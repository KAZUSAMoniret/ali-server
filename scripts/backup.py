"""Portable database + media backup. Restore only into a stopped, explicitly named target."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pg_environment(db):
    env = os.environ.copy()
    env.update(PGHOST=str(db.get('HOST') or '127.0.0.1'), PGPORT=str(db.get('PORT') or 5432),
               PGUSER=db['USER'], PGPASSWORD=db.get('PASSWORD', ''), PGDATABASE=db['NAME'])
    return env


def make_backup(db, media_root, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    with tempfile.TemporaryDirectory(prefix='.working-', dir=output) as temp:
        stage = Path(temp)
        backend = 'postgresql' if db['ENGINE'].endswith('postgresql') else 'sqlite'
        filename = 'database.dump' if backend == 'postgresql' else 'database.sqlite3'
        if backend == 'postgresql':
            subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-acl', '--file', str(stage / filename)],
                           env=pg_environment(db), check=True)
        else:
            with closing(sqlite3.connect(db['NAME'])) as source, closing(sqlite3.connect(stage / filename)) as dest:
                source.backup(dest)
        # Stored photos are immutable; snapshot DB before copying media. Extra new photos are harmless.
        media_root = Path(media_root)
        if media_root.exists():
            shutil.copytree(media_root, stage / 'media', symlinks=False)
        files = {p.relative_to(stage).as_posix(): digest(p) for p in stage.rglob('*') if p.is_file()}
        manifest = {'version': 1, 'backend': backend, 'created_utc': stamp, 'files': files}
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        archive = output / f'life-blog-{stamp}-{time.time_ns() % 1000000:06d}.zip'
        temporary = stage / 'result.zip'
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as target:
            for name in [*files, 'manifest.json']:
                target.write(stage / name, name)
        temporary.replace(archive)
    cutoff = time.time() - 7 * 86400
    for old in output.glob('life-blog-*.zip'):
        if old.is_file() and old.stat().st_mtime < cutoff:
            old.unlink()
    return archive


def verified_extract(archive, stage):
    stage = Path(stage)
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        if len(names) != len(set(names)) or 'manifest.json' not in names:
            raise ValueError('Invalid or duplicate archive members.')
        manifest = json.loads(source.read('manifest.json'))
        if manifest.get('version') != 1 or manifest.get('backend') not in {'sqlite', 'postgresql'}:
            raise ValueError('Unsupported backup format.')
        expected = manifest['files']
        if set(names) != set(expected) | {'manifest.json'}:
            raise ValueError('Archive files do not match manifest.')
        database_name = 'database.dump' if manifest['backend'] == 'postgresql' else 'database.sqlite3'
        if database_name not in expected:
            raise ValueError('Database snapshot is missing.')
        for name, checksum in expected.items():
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe archive path.')
            if name != database_name and not name.startswith('media/'):
                raise ValueError('Unexpected archive member.')
            destination = stage.joinpath(*path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open(name) as incoming, destination.open('wb') as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            if digest(destination) != checksum:
                raise ValueError('Checksum mismatch: ' + name)
    return manifest


def restore_backup(db, media_root, archive, confirmation):
    if confirmation != str(db['NAME']):
        raise ValueError('--confirm-restore must exactly match the destination database name/path.')
    media_root = Path(media_root)
    if media_root.exists() and any(media_root.iterdir()):
        raise ValueError('Media target must be empty. Stop the app and move existing media aside first.')
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        manifest = verified_extract(archive, stage)
        backend = 'postgresql' if db['ENGINE'].endswith('postgresql') else 'sqlite'
        if manifest['backend'] != backend:
            raise ValueError('Backup and destination database backends differ.')
        if backend == 'postgresql':
            subprocess.run(['pg_restore', '--clean', '--if-exists', '--no-owner', '--no-acl',
                            '--single-transaction', '--dbname', db['NAME'], str(stage / 'database.dump')],
                           env=pg_environment(db), check=True)
        else:
            Path(db['NAME']).parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(stage / 'database.sqlite3')) as source, closing(sqlite3.connect(db['NAME'])) as dest:
                source.backup(dest)
        if (stage / 'media').exists():
            shutil.copytree(stage / 'media', media_root, dirs_exist_ok=True)
        else:
            media_root.mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    backup = sub.add_parser('backup')
    backup.add_argument('--output', required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('archive')
    restore = sub.add_parser('restore')
    restore.add_argument('archive')
    restore.add_argument('--confirm-restore', required=True, help='Exact destination database name; existing DB content is replaced.')
    args = parser.parse_args()
    if args.action == 'verify':
        with tempfile.TemporaryDirectory() as temp:
            manifest = verified_extract(args.archive, temp)
        print(f"Verified {len(manifest['files'])} files ({manifest['backend']}).")
        return
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.db import connections
    db = dict(settings.DATABASES['default'])
    connections.close_all()
    if args.action == 'backup':
        print(make_backup(db, settings.MEDIA_ROOT, args.output))
    else:
        restore_backup(db, settings.MEDIA_ROOT, args.archive, args.confirm_restore)
        print('Restore complete. Check the site before restarting public traffic.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f'Backup operation failed: {exc}', file=sys.stderr)
        sys.exit(1)
