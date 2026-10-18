"""Run only with a disposable PostgreSQL connection whose role has CREATEDB."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlparse, urlunparse
import uuid

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.backup import make_backup, restore_backup

ROOT = Path(__file__).resolve().parent.parent


def main():
    url = os.environ.get('DATABASE_URL', '')
    if not url.startswith(('postgresql://', 'postgres://')):
        raise SystemExit('Set DATABASE_URL to a disposable PostgreSQL test connection with CREATEDB.')
    parsed = urlparse(url)
    suffix = uuid.uuid4().hex[:12]
    source_name, target_name = 'blog_smoke_' + suffix, 'blog_restore_' + suffix
    db = {'ENGINE': 'django.db.backends.postgresql', 'NAME': source_name,
          'HOST': parsed.hostname, 'PORT': parsed.port or 5432,
          'USER': unquote(parsed.username or ''), 'PASSWORD': unquote(parsed.password or '')}
    created = []
    with psycopg.connect(url, autocommit=True) as admin:
        try:
            for name in (source_name, target_name):
                admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
                created.append(name)
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                env = os.environ.copy()
                env.update(DATABASE_URL=urlunparse(parsed._replace(path='/' + source_name)),
                           MEDIA_ROOT=str(root / 'source-media'), DJANGO_ENV='development')
                subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], cwd=ROOT, env=env, check=True)
                seed = """
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from blog.images import normalize_image
from blog.models import Post, Photo
p = Post.objects.create(title='Recovery verification', status='published')
b = BytesIO()
Image.new('RGB', (40, 20), 'green').save(b, format='PNG')
Photo.objects.create(post=p, file=normalize_image(SimpleUploadedFile('test.png', b.getvalue())))
"""
                subprocess.run([sys.executable, 'manage.py', 'shell', '-c', seed], cwd=ROOT, env=env, check=True)
                archive = make_backup(db, root / 'source-media', root / 'backups')
                restore_backup(dict(db, NAME=target_name), root / 'restored-media', archive, target_name)
                with psycopg.connect(urlunparse(parsed._replace(path='/' + target_name))) as restored:
                    assert restored.execute('SELECT title FROM blog_post').fetchone()[0] == 'Recovery verification'
                    filename = restored.execute('SELECT file FROM blog_photo').fetchone()[0]
                assert (root / 'source-media' / filename).read_bytes() == (root / 'restored-media' / filename).read_bytes()
                env.update(DATABASE_URL=urlunparse(parsed._replace(path='/' + target_name)), MEDIA_ROOT=str(root / 'restored-media'),
                           ALLOWED_HOSTS='testserver,localhost,127.0.0.1')
                check = """
from django.test import Client
from blog.models import Post, Photo
c = Client()
p, photo = Post.objects.get(), Photo.objects.get()
assert c.get(p.get_absolute_url()).status_code == 200
r = c.get(photo.get_absolute_url())
assert r.status_code == 200
r.close()
p.status = 'draft'
p.save()
assert c.get(p.get_absolute_url()).status_code == 404
assert c.get(photo.get_absolute_url()).status_code == 404
"""
                subprocess.run([sys.executable, 'manage.py', 'shell', '-c', check], cwd=ROOT, env=env, check=True)
                print('PostgreSQL migration, publication, withdrawal, database and photo restore: PASS')
        finally:
            for name in reversed(created):
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


if __name__ == '__main__':
    main()
