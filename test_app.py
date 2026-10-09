import asyncio
import functools
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import app as module
from app import App, download_media
from yanhe import Yanhe, media_streams, normalize_replays, safe_name, rewrite_playlist


class ParserTest(unittest.TestCase):
    def test_nested_replays_and_streams(self):
        ready = {"id": "1", "sub_title": "已有回放", "class_begin": "10", "playback_status": "1", "sub_status": "6"}
        future = {"id": "2", "sub_title": "未来课时", "class_begin": "20", "playback_status": "0", "sub_status": "2"}
        hidden = dict(ready, id="3", show="no")
        rows = normalize_replays({"sub_list": {"2026": {"10": {"2": [ready, future, hidden, ready]}}}})
        self.assertEqual([(r["id"], r["ready"]) for r in rows], [("1", True), ("2", False)])
        self.assertEqual(rows[1]["status"], "未开始")
        self.assertEqual(safe_name('../课堂/回放?'), '_课堂_回放_')
        streams = media_streams({"video_list": {"0": {"type": "3", "status": "2", "duration": "12", "preview_url": "https://example.org/live.m3u8"},
            "1": {"type": "2", "status": "1", "preview_url": "https://example.org/not-ready.mp4"}}})
        self.assertEqual(set(streams), {"teacher"})
        rewritten = rewrite_playlist('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key"\npart.ts\n',
           'https://example.org/video/list.m3u8', {'https://example.org/video/part.ts': 'https://example.org/video/part.ts?t=per-segment'})
        self.assertIn('URI="https://example.org/video/key"', rewritten)
        self.assertIn('part.ts?t=per-segment', rewritten)


class PaginationTest(unittest.IsolatedAsyncioTestCase):
    async def test_all_pages_and_duplicate_guard(self):
        client = Yanhe(Path(tempfile.gettempdir()))
        calls = []
        async def fake_api(path, params):
            page = params["nowpage"]
            calls.append(page)
            ids = [1, 2] if page == 1 else [3]
            return {"params": {"result": {"total": 3, "data": [{"Id": i, "Title": str(i)} for i in ids]}}}
        client.api = fake_api
        self.assertEqual(len(await client.courses()), 3)
        self.assertEqual(calls, [1, 2])
        async def repeated(path, params):
            return {"params": {"result": {"total": 4, "data": [{"Id": 1, "Title": "same"}]}}}
        client.api = repeated
        with self.assertRaisesRegex(ValueError, "重复"):
            await client.courses()


class QueueTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.state_patch = patch.object(module, "STATE", self.directory)
        self.state_patch.start()
        self.app = App(self.directory / "downloads", 2)
        self.app.courses = [{"id": "1", "title": "课程A", "term": "2026"}, {"id": "2", "title": "课程B", "term": "2026"}]
        async def replays(cid):
            return [{"id": "10", "title": "第一节", "ready": True}, {"id": "11", "title": "未开始", "ready": False}]
        self.app.yanhe.replays = replays

    async def asyncTearDown(self):
        self.state_patch.stop()
        self.temp.cleanup()

    async def test_batch_dedup_cancel_retry_and_recovery(self):
        request = {"items": [{"course_id": "1", "sub_id": "10"}, {"course_id": "1", "sub_id": "10"}, {"course_id": "2", "sub_id": "10"}], "streams": ["teacher", "ppt"]}
        self.assertEqual((await self.app.action('/api/queue', request))["added"], 4)
        self.assertEqual((await self.app.action('/api/queue', request))["added"], 0)
        with self.assertRaisesRegex(ValueError, "未开始"):
            await self.app.action('/api/queue', {"items": [{"course_id": "1", "sub_id": "11"}]})
        job = self.app.jobs[0]
        await self.app.action('/api/cancel', {"id": job["id"]})
        self.assertEqual(job["status"], "cancelled")
        async def resolve(cid, sid, kind): return {"duration": 2}
        self.app.yanhe.resolve = resolve
        def fake_download(source, destination, progress, cancelled):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b'complete test video')
            progress({"progress": 90})
        with patch.object(module, "download_media", fake_download):
            worker = asyncio.create_task(self.app.worker())
            await self.app.pending.join()
            await self.app.action('/api/retry', {"id": job["id"]})
            await self.app.pending.join()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        self.assertTrue(all(j["status"] == "done" for j in self.app.jobs))
        self.assertEqual((await self.app.action('/api/queue', request))["added"], 0)
        job["status"] = 'downloading'
        self.app.persist()
        recovered = App(None, 2)
        self.assertEqual(recovered.jobs[0]["status"], 'cancelled')
        job['status'] = 'done'
        destination = str(self.directory / 'new-downloads')
        await self.app.action('/api/settings', {"outdir": destination})
        self.assertEqual(App(None, 2).outdir, Path(destination).resolve())

    async def test_one_failure_does_not_block_next_job(self):
        await self.app.action('/api/queue', {"items": [{"course_id": "1", "sub_id": "10"}], "streams": ["ppt", "teacher"]})
        async def resolve(cid, sid, kind):
            if kind == 'ppt': raise ValueError('没有PPT画面')
            return {"duration": 2}
        self.app.yanhe.resolve = resolve
        def fake_download(source, destination, progress, cancelled):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b'video')
        with patch.object(module, 'download_media', fake_download):
            worker = asyncio.create_task(self.app.worker())
            await self.app.pending.join()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        self.assertEqual([j['status'] for j in self.app.jobs], ['failed', 'done'])


class SilentHTTP(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


@unittest.skipUnless(shutil.which('ffmpeg'), '需要 FFmpeg 运行下载测试')
class DownloadTest(unittest.TestCase):
    def test_mp4_hls_and_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=12',
                            '-t', '2', '-c:v', 'libx264', '-g', '12', '-pix_fmt', 'yuv420p', str(root / 'source.mp4')], check=True)
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(root / 'source.mp4'), '-c', 'copy',
                            '-hls_time', '1', '-hls_list_size', '0', str(root / 'source.m3u8')], check=True)
            server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(SilentHTTP, directory=directory))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                origin = f'http://127.0.0.1:{server.server_port}'
                for ext in ['mp4', 'm3u8', 'manifest']:
                    actual_ext = 'm3u8' if ext == 'manifest' else ext
                    source = {'url': origin + '/source.' + actual_ext, 'referer': origin, 'user_agent': 'test', 'cookies': []}
                    if ext == 'manifest':
                        source['manifest'] = rewrite_playlist((root/'source.m3u8').read_text(), source['url'], {})
                    destination = root / ('saved-' + ext + '.mp4')
                    updates = []
                    download_media(source, destination, updates.append, threading.Event())
                    self.assertGreater(destination.stat().st_size, 100)
                    self.assertTrue(updates)
                    metadata = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,format_name','-of','json',str(destination)], capture_output=True, text=True, check=True)
                    output = json.loads(metadata.stdout)['format']
                    self.assertGreater(float(output['duration']), 1)
                    self.assertIn('mp4', output['format_name'])
                cancelled = threading.Event()
                cancelled.set()
                with self.assertRaises(Exception):
                    download_media(source, root/'cancelled.mp4', lambda data: None, cancelled)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
