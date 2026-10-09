import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import App
from desktop import prepare_data, instance_lock
from library import Library, write_json


class LibraryTest(unittest.TestCase):
    def test_import_scan_missing_file_and_new_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            library = Library(root)
            folder = root / 'downloads/2026/课程_12'
            folder.mkdir(parents=True)
            video = folder / '第1节_34_教师画面.mp4'
            video.write_bytes(b'local video')
            self.assertEqual(library.scan(root / 'downloads', []), 1)
            self.assertEqual(library.file('12', '34', 'teacher')['path'], str(video.resolve()))
            old = [{'id': '34', 'title': '第1节', 'ready': True}, {'id': '35', 'title': '第2节', 'ready': False}]
            library.update_replays('12', old)
            self.assertFalse(any(r['is_new'] for r in old))
            new = [dict(old[0]), dict(old[1], ready=True), {'id': '36', 'title': '第3节', 'ready': True}]
            library.update_replays('12', new)
            rows = library.decorate('12', new, [])
            self.assertEqual([r['is_new'] for r in rows], [False, True, True])
            self.assertEqual(rows[0]['downloaded'], ['teacher'])
            # Refreshing again must retain the new markers across application restarts.
            library.update_replays('12', [dict(r) for r in new])
            self.assertTrue(Library(root).data['replays']['12'][1]['is_new'])
            video.unlink()
            self.assertIsNone(library.file('12', '34', 'teacher'))
            self.assertEqual(library.scan(root / 'downloads', []), 0)
            self.assertFalse(library.data['files']['12:34:teacher']['exists'])

    def test_migration_keeps_video_location_and_excludes_other_private_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = root / 'old', root / 'data'
            (old / '.state').mkdir(parents=True)
            (old / 'downloads').mkdir()
            write_json(old / '.state/jobs.json', [])
            (old / '.state/private-script.py').write_text('private')
            prepare_data(new, old)
            self.assertEqual(json.loads((new / 'settings.json').read_text())['outdir'], str((old / 'downloads').resolve()))
            self.assertFalse((new / 'private-script.py').exists())
            write_json(new / 'settings.json', {'outdir': 'chosen later'})
            prepare_data(new, old)
            self.assertEqual(json.loads((new / 'settings.json').read_text())['outdir'], 'chosen later')
            with instance_lock(new):
                with self.assertRaisesRegex(ValueError, '已经运行'):
                    with instance_lock(new):
                        pass


class TrackingTest(unittest.IsolatedAsyncioTestCase):
    async def test_manual_tracking_opt_in_auto_download_and_inventory_dedup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = App(root / 'videos', 2, root)
            app.courses = [{'id': '12', 'title': '课程', 'term': '2026'}]
            app.library.data['courses'] = app.courses
            available = [{'id': '34', 'title': '第1节', 'ready': True}]
            async def status(): return {'logged_in': True, 'name': 'test'}
            async def replays(cid): return [dict(r) for r in available]
            app.yanhe.status, app.yanhe.replays = status, replays
            await app.action('/api/track', {'course_id': '12', 'tracked': True})
            await app.sync()
            self.assertEqual(app.jobs, [])  # Following alone must not trigger a download.
            available.append({'id': '35', 'title': '第2节', 'ready': True})
            result = await app.sync()
            self.assertEqual(result['new'], 1)
            folder = root / 'videos/2026/课程_12'
            folder.mkdir(parents=True)
            (folder / '第1节_34_教师画面.mp4').write_bytes(b'previous download')
            app.library.scan(app.outdir, [])
            await app.action('/api/track', {'course_id': '12', 'tracked': True, 'auto_download': True})
            with patch('app.shutil.which', return_value='/ffmpeg'):
                result = await app.sync()
                self.assertEqual(result['added'], 1)
                self.assertEqual(app.jobs[0]['sub_id'], '35')
                self.assertEqual((await app.sync())['added'], 0)
            summary = app.snapshot()['courses'][0]
            self.assertEqual((summary['downloaded_count'], summary['pending_count']), (1, 1))
            app.save_settings()
            recovered = App(None, 2, root)
            self.assertTrue(recovered.snapshot()['courses'][0]['auto_download'])
            self.assertEqual(recovered.outdir, app.outdir)
            self.assertEqual(recovered.jobs[0]['status'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
