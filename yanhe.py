"""The new Yanhe platform's APIs, verified against the actual BIT website."""
import asyncio
import re
from pathlib import Path
from urllib.parse import urlencode, unquote, urlsplit, urljoin

from playwright.async_api import async_playwright

ORIGIN = "https://aita.yanhekt.cn"
HOME = ORIGIN + "/education/?tenant_code=21#/home?menu_code=C-xswdkc,-1"
STREAM_NAMES = {"teacher": "教师画面", "ppt": "PPT画面", "student": "学生画面"}
STREAM_TYPES = {"2": "ppt", "3": "teacher", "4": "student"}


def safe_name(value):
    return re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", str(value)).strip(" .")[:120] or "未命名"


def flatten_subjects(value):
    if isinstance(value, list):
        for child in value:
            yield from flatten_subjects(child)
    elif isinstance(value, dict):
        if "sub_title" in value and "id" in value:
            yield value
        else:
            for child in value.values():
                yield from flatten_subjects(child)


def normalize_replays(detail):
    result = []
    seen = set()
    for row in flatten_subjects(detail.get("sub_list", {})):
        if str(row.get("sub_delete", "0")) != "0" or row.get("show") == "no":
            continue
        sid = str(row["id"])
        if sid in seen:
            continue
        seen.add(sid)
        # Verified: playback_status=1 and sub_status=6 means available replay.
        ready = str(row.get("playback_status")) == "1"
        status = "可下载" if ready else ("未开始" if str(row.get("sub_status")) == "2" else "暂无回放")
        result.append({"id": sid, "title": row["sub_title"], "teacher": row.get("lecturer_name", ""),
                       "begin": int(row.get("class_begin") or 0), "ready": ready, "status": status})
    return sorted(result, key=lambda row: (row["begin"], row["id"]))


def media_streams(info):
    videos = info.get("video_list") or {}
    videos = videos.values() if isinstance(videos, dict) else videos
    result = {}
    for row in videos:
        kind = STREAM_TYPES.get(str(row.get("type")))
        url = row.get("preview_url")
        if kind and url and str(row.get("status")) == "2":
            result[kind] = {"url": url, "duration": int(float(row.get("duration") or 0))}
    return result


def rewrite_playlist(playlist, base, signed):
    """Resolve every HLS URI, including keys/maps, relative to the remote playlist."""
    def replace(uri):
        absolute = urljoin(base, uri)
        return signed.get(absolute, absolute)
    lines = []
    for line in playlist.splitlines():
        if line.startswith('#'):
            line = re.sub(r'URI="([^"]+)"', lambda m: 'URI="' + replace(m[1]) + '"', line)
        elif line.strip():
            line = replace(line.strip())
        lines.append(line)
    return '\n'.join(lines) + '\n'


class Yanhe:
    def __init__(self, state_dir):
        self.state_file = Path(state_dir) / "session.json"
        self.lock = asyncio.Lock()
        self.pw = self.browser = self.context = self.login_page = None

    async def ensure(self, headed=False):
        if self.browser and not self.browser.is_connected():
            self.context = self.login_page = None
        if self.context:
            return
        if not self.pw:
            self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=not headed)
        self.context = await self.browser.new_context(
            storage_state=str(self.state_file) if self.state_file.exists() else None)

    async def headers(self):
        await self.ensure()
        for cookie in await self.context.cookies(ORIGIN):
            if cookie["name"] == "_token":
                match = re.search(r'"_token";i:\d+;s:\d+:"([^"]+)"', unquote(cookie["value"]))
                if match:
                    return {"Authorization": "Bearer " + match[1], "Referer": HOME,
                            "Accept": "application/json", "Accept-Language": "zh_cn"}
        raise ValueError("请先完成北理统一认证登录")

    async def api(self, path, params=None):
        headers = await self.headers()
        response = await self.context.request.get(ORIGIN + path, params=params, headers=headers, timeout=30000)
        try:
            if response.status in (401, 403):
                raise ValueError("登录已失效或无访问权限，请重新登录")
            if not response.ok:
                raise ValueError(f"课程网站请求失败（HTTP {response.status}），请稍后重试")
            try:
                data = await response.json()
            except Exception:
                raise ValueError("课程网站返回了非 JSON 内容，请重新登录或稍后重试") from None
            if data.get("code") not in (None, 0, 200, 1000, 10000):
                raise ValueError(str(data.get("msg") or data.get("message") or "课程接口拒绝访问"))
            return data
        finally:
            await response.dispose()

    async def status(self):
        async with self.lock:
            try:
                data = await self.api("/userapi/v1/infosimple")
                user = data.get("params") or data.get("data") or {}
                await self.save()
                return {"logged_in": True, "name": user.get("realname", "已登录"), "login_open": False}
            except ValueError as exc:
                return {"logged_in": False, "name": "", "login_open": bool(self.login_page and not self.login_page.is_closed()), "message": str(exc)}

    async def save(self):
        await self.context.storage_state(path=str(self.state_file))
        self.state_file.chmod(0o600)

    async def login(self):
        async with self.lock:
            if self.browser and not self.browser.is_connected():
                self.context = self.login_page = None
            if self.login_page and not self.login_page.is_closed():
                await self.login_page.bring_to_front()
                return {"message": "请在认证窗口完成登录，再点击“检查登录”"}
            if self.context:
                await self.save()
                await self.browser.close()
                self.context = None
            await self.ensure(headed=True)
            self.login_page = await self.context.new_page()
            service = ORIGIN + "/casapi/index.php?" + urlencode({"auType": "cas", "forward": HOME,
                        "r": "auth/login", "tenant_code": "21"})
            await self.login_page.goto("https://sso.bit.edu.cn/cas/login?" + urlencode({"service": service}), wait_until="domcontentloaded")
            return {"message": "请在认证窗口完成登录，再点击“检查登录”"}

    async def courses(self):
        async with self.lock:
            result, seen, page = [], set(), 1
            while True:
                data = await self.api("/personal/courseapi/vlabpassportapi/v1/account-profile/course",
                                      {"nowpage": page, "per-page": 50})
                payload = data.get("params", {}).get("result")
                if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                    raise ValueError("课程列表接口结构已变化，请检查新版网站")
                rows = payload["data"]
                added = 0
                for row in rows:
                    cid = str(row["Id"])
                    if cid not in seen:
                        seen.add(cid)
                        added += 1
                        result.append({"id": cid, "title": row["Title"], "teacher": row.get("Teacher", ""),
                                       "term": row.get("TermName", ""), "department": row.get("KkxyName", ""),
                                       "lesson_count": row.get("progress", {}).get("subjectNum", 0)})
                if len(result) >= int(payload["total"]):
                    break
                if not added:
                    raise ValueError("课程分页返回重复或空页面，请重试")
                page += 1
            return result

    async def replays(self, course_id):
        async with self.lock:
            detail = (await self.api("/courseapi/v3/multi-search/get-course-detail", {"course_id": course_id})).get("data")
            if not isinstance(detail, dict) or "sub_list" not in detail:
                raise ValueError("课程回放接口结构已变化或无访问权限")
            return normalize_replays(detail)

    async def resolve(self, course_id, sub_id, kind):
        """Use the website player to get its own fresh CDN-signed URL."""
        async with self.lock:
            info = (await self.api("/courseapi/v3/portal-home-setting/get-sub-info",
                                  {"course_id": course_id, "sub_id": sub_id})).get("data", {})
            streams = media_streams(info)
            if kind not in streams:
                raise ValueError(f"这节回放没有{STREAM_NAMES[kind]}，可换一个画面重试")
            target = urlsplit(streams[kind]["url"]).path
            future = asyncio.get_running_loop().create_future()
            segment_futures = {}
            page = await self.context.new_page()
            referer = ORIGIN + "/livingroom?" + urlencode({"course_id": course_id, "sub_id": sub_id, "tenant_code": 21})

            def capture(request):
                parsed = urlsplit(request.url)
                if parsed.path == target and re.search(r"(?:^|&)t=", parsed.query) and not future.done():
                    future.set_result(request.url)
                if parsed.path in segment_futures and re.search(r"(?:^|&)t=", parsed.query):
                    waiting = segment_futures[parsed.path]
                    if not waiting.done():
                        waiting.set_result(request.url)

            page.on("request", capture)
            # Capture the URLs without streaming hours of video into Chromium.
            await page.route(re.compile(r"\.(?:mp4|m3u8|ts)(?:\?|$)"), lambda route: route.abort())
            try:
                await page.goto(referer, wait_until="domcontentloaded", timeout=30000)
                url = await asyncio.wait_for(future, timeout=30)
                manifest = None
                if urlsplit(url).path.endswith('.m3u8'):
                    # The site's XHR wrapper signs EACH .ts path. A playlist token
                    # cannot be reused for segments. Ask the real wrapper to sign
                    # requests, intercept them before transmission, and rewrite URIs.
                    response = await self.context.request.get(url, headers={"Referer": referer}, timeout=30000)
                    try:
                        if not response.ok:
                            raise ValueError(f"视频源无法访问（HTTP {response.status}）")
                        playlist = await response.text()
                    finally:
                        await response.dispose()
                    if '#EXTM3U' not in playlist:
                        raise ValueError('播放列表无效，请重新登录后重试')
                    if '#EXT-X-STREAM-INF' in playlist:
                        raise ValueError('此回放使用多码率主播放列表，当前版本暂不支持')
                    uris = [urljoin(url, line.strip()) for line in playlist.splitlines() if line.strip() and not line.startswith('#')]
                    ts_uris = list(dict.fromkeys(uri for uri in uris if urlsplit(uri).path.lower().endswith('.ts')))
                    segment_futures = {urlsplit(uri).path: asyncio.get_running_loop().create_future() for uri in ts_uris}
                    await page.evaluate("""urls => {
                        for (const url of urls) {
                            const xhr = new XMLHttpRequest();
                            xhr.open('GET', url, true);
                            xhr.send();
                        }
                    }""", ts_uris)
                    signed_urls = await asyncio.wait_for(asyncio.gather(*(segment_futures[urlsplit(uri).path] for uri in ts_uris)), timeout=30)
                    manifest = rewrite_playlist(playlist, url, dict(zip(ts_uris, signed_urls)))
                cookies = await self.context.cookies()
                user_agent = await page.evaluate("navigator.userAgent")
                return {"url": url, "referer": referer, "cookies": cookies,
                        "user_agent": user_agent, "duration": streams[kind]["duration"], "manifest": manifest}
            except asyncio.TimeoutError:
                raise ValueError("播放器未返回有效下载地址，请检查登录状态或稍后重试") from None
            finally:
                await page.close()

    async def close(self):
        if self.context and self.browser.is_connected():
            await self.save()
            await self.browser.close()
        if self.pw:
            await self.pw.stop()
