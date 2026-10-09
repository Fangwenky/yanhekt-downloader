"""Native macOS / Windows window around the local course manager."""
import argparse
import asyncio
import json
import os
import queue
import shutil
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import webview

from app import main


def user_data_dir():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/YanhektDownloader'
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / 'YanhektDownloader'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'yanhekt-downloader'


def prepare_data(directory, legacy=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if legacy:
        legacy = Path(legacy)
        for name in ('session.json', 'jobs.json', 'settings.json', 'library.json'):
            source, target = legacy / '.state' / name, directory / name
            if source.is_file() and not target.exists():
                shutil.copy2(source, target)
                target.chmod(0o600)
        if not (directory / 'settings.json').exists() and (legacy / 'downloads').is_dir():
            from library import write_json
            write_json(directory / 'settings.json', {'outdir': str((legacy / 'downloads').resolve()), 'check_minutes': 60})
    return directory


class Desktop:
    window = None

    def choose_folder(self):
        result = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None


@contextmanager
def instance_lock(directory):
    """Keep simultaneous launches from writing the same local library."""
    handle = open(Path(directory) / 'desktop.lock', 'a+b')
    try:
        if sys.platform == 'win32':
            import msvcrt
            handle.seek(0)
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise ValueError('延河课堂已经运行，请使用已打开的软件窗口') from None
    try:
        yield
    finally:
        handle.close()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir')
    parser.add_argument('--migrate-from', help='导入旧版工具的本地记录，保留原视频位置')
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--ui-smoke-test', action='store_true')
    args = parser.parse_args()
    frozen = bool(getattr(sys, 'frozen', False))
    resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    if frozen:
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(resources / 'browsers')
        os.environ['PATH'] = str(resources / 'bin') + os.pathsep + os.environ.get('PATH', '')
    if args.smoke_test:
        # Run from the packaged executable, using only packaged browser/FFmpeg.
        import subprocess
        from playwright.sync_api import sync_playwright
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='chromium')
            page = browser.new_page()
            page.set_content('<h1>Yanhekt</h1>')
            assert page.locator('h1').inner_text() == 'Yanhekt'
            browser.close()
        if args.state_dir:
            Path(args.state_dir).mkdir(parents=True, exist_ok=True)
            (Path(args.state_dir) / 'smoke-ok.txt').write_text('browser + ffmpeg OK', encoding='utf-8')
        return
    legacy = args.migrate_from or (str(resources) if not frozen else None)
    directory = prepare_data(args.state_dir or user_data_dir(), legacy)
    if sys.stdout is None:
        log = open(directory / 'desktop.log', 'a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log
    with instance_lock(directory):
        launch(directory, args.ui_smoke_test)


def launch(directory, ui_smoke=False):
    desktop, stop, started = Desktop(), threading.Event(), queue.Queue()
    videos = 'Videos' if sys.platform == 'win32' else 'Movies'
    settings = SimpleNamespace(outdir=None, default_outdir=str(Path.home() / videos / '延河课堂'),
        concurrency=2, state_dir=str(directory), port=0, no_open=True)
    def serve():
        try:
            asyncio.run(main(settings, ready=started.put, external_stop=stop, desktop=desktop))
        except Exception as exc:
            started.put(exc)
    service = threading.Thread(target=serve, daemon=True)
    service.start()
    result = started.get(timeout=30)
    if isinstance(result, Exception):
        raise result
    desktop.window = webview.create_window('延河课堂 · 课程管理', result, width=1280, height=900, min_size=(840, 600), hidden=ui_smoke)
    if ui_smoke:
        # Bound GUI checks on unattended build machines. AppKit can keep its
        # event loop alive after closing a hidden test window.
        threading.Timer(60, lambda: os._exit(1)).start()
        def loaded():
            valid = False
            try:
                valid = desktop.window.evaluate_js("document.getElementById('course-title').textContent === '选择一门课程' && document.querySelectorAll('.tabs button').length === 3")
                if valid:
                    (directory / 'ui-ok.txt').write_text('native window + local UI OK', encoding='utf-8')
            finally:
                stop.set()
                service.join(timeout=10)
                os._exit(0 if valid else 1)
        desktop.window.events.loaded += loaded
    desktop.window.events.closed += stop.set
    try:
        webview.start()
    finally:
        stop.set()
        service.join(timeout=90)


if __name__ == '__main__':
    run()
