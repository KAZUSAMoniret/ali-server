import json
import hashlib
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import zipfile
from django.test import SimpleTestCase
from scripts.backup import make_backup, restore_backup, verified_extract

class BackupTests(SimpleTestCase):
    def test_sqlite_database_and_photo_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(root / 'source.db')}
            with closing(sqlite3.connect(db['NAME'])) as conn:
                conn.execute('CREATE TABLE notes (body TEXT)')
                conn.execute('INSERT INTO notes VALUES (?)', ('生活手记',))
                conn.commit()
            media = root / 'source-media'
            media.mkdir()
            (media / 'photo.webp').write_bytes(b'photo-content-for-restore-test')
            archive = make_backup(db, media, root / 'backups')
            target_db = dict(db, NAME=str(root / 'restored.db'))
            restore_backup(target_db, root / 'restored-media', archive, target_db['NAME'])
            with closing(sqlite3.connect(target_db['NAME'])) as conn:
                self.assertEqual(conn.execute('SELECT body FROM notes').fetchone()[0], '生活手记')
            self.assertEqual((root / 'restored-media/photo.webp').read_bytes(), (media / 'photo.webp').read_bytes())
            with self.assertRaises(ValueError):
                restore_backup(target_db, root / 'unused', archive, 'wrong-database')

    def test_tampered_backup_rejected_before_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'corrupt.zip'
            with zipfile.ZipFile(archive, 'w') as target:
                target.writestr('manifest.json', json.dumps({'version': 1, 'backend': 'sqlite', 'files': {'database.sqlite3': 'bad'}}))
                target.writestr('database.sqlite3', b'changed-data')
            with self.assertRaises(ValueError):
                verified_extract(archive, root / 'staging')

    def test_archive_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'unsafe.zip'
            with zipfile.ZipFile(archive, 'w') as target:
                target.writestr('manifest.json', json.dumps({'version': 1, 'backend': 'sqlite',
                                'files': {'database.sqlite3': hashlib.sha256(b'bad').hexdigest(), 'media/../../escape': 'bad'}}))
                target.writestr('database.sqlite3', b'bad')
                target.writestr('media/../../escape', b'bad')
            with self.assertRaises(ValueError):
                verified_extract(archive, root / 'staging')
            self.assertFalse((root / 'escape').exists())
