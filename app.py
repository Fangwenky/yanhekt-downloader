"""Local web UI + authenticated API client + resumable download queue."""
import argparse
import asyncio
import http.cookiejar
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL

from yanhe import Yanhe, STREAM_NAMES, safe_name

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".state"


def write_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(path)


class QuietLogger:
    def debug(self, message): pass
    def warning(self, message): pass
    def error(self, message): pass


def download_media(source, destination, progress, cancelled):
    def hook(data):
        if cancelled.is_set():
            raise RuntimeError("下载已取消")
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        fragment_count = data.get("fragment_count")
        percent = (data.get("downloaded_bytes", 0) / total * 100 if total else
                   data.get("fragment_index", 0) / fragment_count * 100 if fragment_count else None)
        progress({"progress": min(99, round(percent, 1)) if percent is not None else None,
                  "bytes": data.get("downloaded_bytes", 0), "speed": data.get("speed"),
                  "eta": data.get("eta"), "status": "processing" if data["status"] == "finished" else "downloading"})

    destination.parent.mkdir(parents=True, exist_ok=True)
    options = {"outtmpl": str(destination).replace("%", "%%"), "quiet": True, "no_warnings": True,
               "logger": QuietLogger(), "progress_hooks": [hook], "continuedl": True,
               "overwrites": False, "retries": 3, "fragment_retries": 3, "socket_timeout": 20,
               "concurrent_fragment_downloads": 2, "skip_unavailable_fragments": False,
               "http_headers": {"Referer": source["referer"], "User-Agent": source["user_agent"]},
               "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]}
    with tempfile.TemporaryDirectory(prefix='yanhe-media-') as temporary:
        url = source['url']
        if source.get('manifest'):
            manifest = Path(temporary) / 'signed.m3u8'
            manifest.write_text(source['manifest'], encoding='utf-8')
            manifest.chmod(0o600)
            url = manifest.as_uri()
            options['enable_file_urls'] = True
        with YoutubeDL(options) as ydl:
            for row in source["cookies"]:
                # A cookie jar preserves domain/path restrictions; never put cookies into global headers.
                domain = row["domain"]
                expires = row.get("expires", -1)
                cookie = http.cookiejar.Cookie(0, row["name"], row["value"], None, False, domain,
                        domain.startswith("."), domain.startswith("."), row["path"], True,
                        row["secure"], int(expires) if expires > 0 else None, expires <= 0,
                        None, None, {"HttpOnly": row.get("httpOnly", False)})
                ydl.cookiejar.set_cookie(cookie)
            ydl.extract_info(url, download=True)
    if cancelled.is_set():
        raise RuntimeError("下载已取消")
    if not destination.is_file() or not destination.stat().st_size:
        raise RuntimeError("下载未生成完整视频文件")


class App:
    def __init__(self, outdir, concurrency):
        self.yanhe = Yanhe(STATE)
        settings = STATE / "settings.json"
        saved = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
        self.outdir = Path(outdir or saved.get("outdir") or ROOT / "downloads").expanduser().resolve()
        self.concurrency = concurrency
        self.courses = []
        self.jobs = []
        self.cancel_events = {}
        self.worker_tasks = []
        self.pending = asyncio.Queue()
        self.auth = {"logged_in": False, "name": ""}
        self.loop = asyncio.get_running_loop()
        path = STATE / "jobs.json"
        if path.exists():
            self.jobs = json.loads(path.read_text(encoding="utf-8"))
            for job in self.jobs:
                if job["status"] in ("queued", "resolving", "downloading", "processing"):
                    job.update(status="cancelled", error="上次运行已中断，点击重试继续下载")

    def persist(self):
        write_json(STATE / "jobs.json", self.jobs)

    def snapshot(self):
        return {"auth": self.auth, "courses": self.courses, "jobs": self.jobs,
                "outdir": str(self.outdir), "concurrency": self.concurrency,
                "ffmpeg": bool(shutil.which("ffmpeg"))}

    async def action(self, path, body):
        if path == "/api/auth/check":
            self.auth = await self.yanhe.status()
            return self.auth
        if path == "/api/auth/login":
            return await self.yanhe.login()
        if path == "/api/courses":
            self.auth = await self.yanhe.status()
            if not self.auth["logged_in"]:
                raise ValueError(self.auth.get("message", "请先登录"))
            self.courses = await self.yanhe.courses()
            return {"courses": self.courses}
        if path == "/api/replays":
            course = self.course(body.get("course_id"))
            return {"replays": await self.yanhe.replays(course["id"])}
        if path == "/api/settings":
            if any(j["status"] in ("queued", "resolving", "downloading", "processing") for j in self.jobs):
                raise ValueError("请等待或取消队列中的任务后修改保存目录")
            value = body.get("outdir")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("请填写保存目录")
            destination = Path(value).expanduser()
            self.outdir = (destination if destination.is_absolute() else ROOT / destination).resolve()
            self.outdir.mkdir(parents=True, exist_ok=True)
            write_json(STATE / "settings.json", {"outdir": str(self.outdir)})
            return {"outdir": str(self.outdir)}
        if path == "/api/queue":
            if not shutil.which("ffmpeg"):
                raise ValueError("需要 FFmpeg 才能下载并合并回放，请先安装 FFmpeg")
            items = body.get("items")
            kinds = body.get("streams", ["teacher"])
            if not isinstance(items, list) or not items or len(items) > 1000:
                raise ValueError("请选择 1 至 1000 节回放")
            if not isinstance(kinds, list) or not kinds or any(k not in STREAM_NAMES for k in kinds):
                raise ValueError("请选择有效的视频画面")
            ready = {}
            planned = []
            existing = {(j["course_id"], j["sub_id"], j["stream"]) for j in self.jobs
                        if j["status"] in ("queued", "resolving", "downloading", "processing") or
                        (j["status"] == "done" and Path(j["path"]).is_file())}
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("回放选择格式错误")
                course = self.course(item.get("course_id"))
                cid = course["id"]
                if cid not in ready:
                    ready[cid] = {r["id"]: r for r in await self.yanhe.replays(cid) if r["ready"]}
                replay = ready[cid].get(str(item.get("sub_id")))
                if not replay:
                    raise ValueError("选择中包含无权限、未开始或暂无回放的课时，请刷新")
                for kind in dict.fromkeys(kinds):
                    key = cid, replay["id"], kind
                    if key in existing:
                        continue
                    existing.add(key)
                    folder = self.outdir / safe_name(course["term"] or "未标记学期") / (safe_name(course["title"]) + "_" + cid)
                    filename = safe_name(replay["title"]) + "_" + replay["id"] + "_" + STREAM_NAMES[kind] + ".mp4"
                    planned.append({"id": secrets.token_hex(8), "course_id": cid, "sub_id": replay["id"],
                          "course": course["title"], "title": replay["title"], "stream": kind,
                          "status": "queued", "progress": 0, "bytes": 0, "error": "", "path": str(folder / filename)})
            self.jobs.extend(planned)
            self.persist()
            for job in planned:
                self.pending.put_nowait(job)
            return {"added": len(planned)}
        if path in ("/api/cancel", "/api/retry"):
            job = next((j for j in self.jobs if j["id"] == body.get("id")), None)
            if not job:
                raise ValueError("下载任务不存在")
            if path == "/api/cancel":
                if job["status"] in ("queued", "resolving", "downloading", "processing"):
                    self.cancel_events.setdefault(job["id"], threading.Event()).set()
                    if job["status"] == "queued":
                        job.update(status="cancelled", error="已取消，可重试继续下载")
            elif job["status"] in ("failed", "cancelled") and job["id"] not in self.cancel_events:
                job.update(status="queued", progress=0, error="")
                self.pending.put_nowait(job)
            elif path == "/api/retry":
                raise ValueError("任务仍在运行或已经完成")
            self.persist()
            return {"ok": True}
        if path == "/api/open-folder":
            self.outdir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "darwin": subprocess.Popen(["open", str(self.outdir)])
            elif sys.platform == "win32": os.startfile(self.outdir)
            else: subprocess.Popen(["xdg-open", str(self.outdir)])
            return {"ok": True}
        raise ValueError("未知操作")

    def course(self, cid):
        course = next((c for c in self.courses if c["id"] == str(cid)), None)
        if not course:
            raise ValueError("请先拉取课程，并选择列表中的课程")
        return course

    async def worker(self):
        while True:
            job = await self.pending.get()
            try:
                if job["status"] != "queued":
                    self.cancel_events.pop(job["id"], None)
                    continue
                cancelled = self.cancel_events.setdefault(job["id"], threading.Event())
                job.update(status="resolving", error="")
                self.persist()
                source = await self.yanhe.resolve(job["course_id"], job["sub_id"], job["stream"])
                if cancelled.is_set():
                    raise RuntimeError("下载已取消")
                job.update(status="downloading", duration=source["duration"])
                def progress(data, target=job):
                    self.loop.call_soon_threadsafe(target.update, data)
                await asyncio.to_thread(download_media, source, Path(job["path"]), progress, cancelled)
                job.update(status="done", progress=100, bytes=Path(job["path"]).stat().st_size, speed=None, eta=None)
            except Exception as exc:
                if self.cancel_events.get(job["id"], threading.Event()).is_set():
                    job.update(status="cancelled", error="已取消，可重试继续下载")
                else:
                    # yt-dlp errors contain signed URLs; keep those out of the UI and logs.
                    message = str(exc) if isinstance(exc, ValueError) else "下载失败，请检查网络、登录状态和 FFmpeg；可点击重试"
                    job.update(status="failed", error=message, speed=None, eta=None)
            finally:
                self.cancel_events.pop(job["id"], None)
                self.persist()
                self.pending.task_done()


def handler(app, token, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args): pass

        def send(self, status, content, content_type="application/json; charset=utf-8"):
            data = content.encode("utf-8") if isinstance(content, str) else json.dumps(content, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def local(self):
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.local():
                return self.send(403, {"error": "仅允许本机访问"})
            path = urlsplit(self.path).path
            if path == "/api/state":
                async def state(): return app.snapshot()
                data = asyncio.run_coroutine_threadsafe(state(), app.loop).result(10)
                return self.send(200, data)
            if path in ("/", "/app.js", "/style.css"):
                file = ROOT / "web" / ("index.html" if path == "/" else path[1:])
                content = file.read_text(encoding="utf-8").replace("__API_TOKEN__", token)
                kind = {"/": "text/html", "/app.js": "text/javascript", "/style.css": "text/css"}[path]
                return self.send(200, content, kind + "; charset=utf-8")
            self.send(404, {"error": "页面不存在"})

        def do_POST(self):
            origin = self.headers.get("Origin")
            if not self.local() or self.headers.get("X-Local-Token") != token or origin not in (None, f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self.send(403, {"error": "请求来源无效，请刷新本地页面"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 1024 * 1024:
                    raise ValueError("请求内容过大")
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict): raise ValueError("请求格式错误")
                future = asyncio.run_coroutine_threadsafe(app.action(urlsplit(self.path).path, body), app.loop)
                result = future.result(300)
                self.send(200, result)
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, {"error": str(exc)})
            except Exception:
                self.send(500, {"error": "操作失败，请检查网络或重新打开认证窗口"})
    return Handler


async def main(args):
    STATE.mkdir(exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    app = App(args.outdir, args.concurrency)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(app, secrets.token_urlsafe(32), args.port))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    app.worker_tasks = [asyncio.create_task(app.worker()) for _ in range(args.concurrency)]
    url = f"http://127.0.0.1:{args.port}"
    print(f"延河课堂下载工具：{url}\n保存目录：{app.outdir}\n按 Ctrl+C 停止", flush=True)
    if not args.no_open: webbrowser.open(url)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: asyncio.get_running_loop().add_signal_handler(sig, stop.set)
        except NotImplementedError: pass
    try:
        await stop.wait()
    finally:
        for event in app.cancel_events.values(): event.set()
        for job in app.jobs:
            if job["status"] == "queued": job.update(status="cancelled", error="程序已退出，可重试继续下载")
        # Let current downloads reach cancellation before closing their browser context.
        await app.pending.join()
        for worker in app.worker_tasks: worker.cancel()
        await asyncio.gather(*app.worker_tasks, return_exceptions=True)
        app.persist()
        await app.yanhe.close()
        await asyncio.to_thread(server.shutdown)
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="新版延河课堂课程录播下载工具")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--outdir", help="覆盖保存目录，默认使用上次保存的目录")
    parser.add_argument("--concurrency", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--no-open", action="store_true")
    asyncio.run(main(parser.parse_args()))
