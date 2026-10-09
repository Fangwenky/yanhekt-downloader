# 延河课堂 · 课程与录播管理

北京理工大学新版[延河课堂](https://aita.yanhekt.cn/education/?tenant_code=21#/home?menu_code=C-xswdkc,-1)的本地桌面软件。支持 **macOS（Apple Silicon）和 Windows（x64）**，通过北理统一认证拉取个人课程，查看回放，长期跟踪更新并批量下载到统一视频目录。

## 下载与安装

在 [Releases](https://github.com/Fangwenky/yanhekt-downloader/releases) 下载对应系统的安装包：

| 系统 | 文件 | 启动方式 |
| --- | --- | --- |
| macOS / Apple Silicon | `Yanhekt-macOS-arm64.zip` | 解压，将「延河课堂.app」放入「应用程序」，双击打开 |
| Windows 10 / 11，64 位 | `Yanhekt-Windows-Setup.exe` | 运行安装向导，通过桌面或开始菜单快捷方式打开 |

安装包内置 Python、Chromium、FFmpeg 和下载器，无需自行安装开发环境。Windows 安装程序会在缺少 WebView2 时通过微软官方引导程序安装，首次安装此组件需要联网。[WebView2 部署说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)。

当前安装包没有 Apple 开发者公证或 Windows 代码签名。macOS 若提示无法验证开发者，可在「系统设置 → 隐私与安全性」中允许打开已下载的应用。Windows 若显示 SmartScreen，可核对下载来源后选择「更多信息 → 仍要运行」。Intel Mac 暂未提供预构建包，可从源码运行或在 Intel Mac 上自行构建。

尚未发布的构建也可从 [GitHub Actions](https://github.com/Fangwenky/yanhekt-downloader/actions/workflows/build-desktop.yml) 的成功运行中下载 Artifacts（需登录 GitHub，保存 30 天）。

## 功能

- **统一认证**：在独立 Chromium 登录窗口使用学校提供的密码、短信、扫码等认证方式，不在软件界面收集密码。
- **个人课程**：分页拉取全部个人课程，按课程名称、教师、学期筛选，查看可下载、未开始或暂无回放的课时。
- **课程跟踪**：保存关注的课程，显示已有回放、已保存课时、待补齐课时与新回放数量。
- **检查更新**：手动检查跟踪课程，也可每 15 / 30 / 60 / 120 分钟检查；定时检查仅在软件运行期间执行。
- **自动补齐**：每门课程单独开启，默认关闭。开启后将下载跟踪画面的全部缺失回放，包含旧课时和后续新回放。
- **批量下载**：勾选课时、多门课程，或一键「补齐缺失回放」；教师、PPT、学生画面分别保存，实际可用画面取决于课程。
- **统一资料库**：在同一个根目录内按学期、课程整理视频，搜索本地文件并使用系统播放器打开；扫描原目录可识别旧版已下载视频。
- **下载队列**：两个并行任务，显示进度、速度和剩余时间，支持取消、失败重试与下载器/服务端允许的断点续传。
- **持久记录**：关闭软件后保留课程缓存、跟踪设置、目录与任务记录；已下载且文件仍存在的视频自动跳过，中断任务下次可手动重试。

## 使用方法

1. 打开软件，点击「统一认证登录」，在弹出的浏览器完成北理认证。回到软件点击「检查登录」，或等待自动检查。登录成功后首次自动拉取课程。
2. 在顶部选择统一的视频保存目录，勾选需要下载的画面。已经使用旧版工具时，选择原来的 `downloads/`，再在「本地资料库」点击「扫描本地文件」。保留原文件名中的课程 ID、课时 ID 和画面标记可正确识别。
3. 选择一门课程，查看回放与保存状态。点击已保存画面旁的播放按钮，可用系统播放器打开视频。
4. 勾选「跟踪这门课程」。跟踪会记住当前下载画面，可用「应用当前画面到跟踪设置」更新；顶部画面选择仍用于手动下载。
5. 点击「检查跟踪课程更新」或设置检查间隔。新增课时或从未生成变为已有回放的课时会标记为新回放；首次检查时已有课时显示为待下载。
6. 点击「补齐缺失回放」下载当前所选画面的缺失文件。如希望每次检查后自动下载，开启该课程的「自动下载缺失回放」。
7. 在「下载队列」查看进度；在「本地资料库」搜索、播放与检查视频。

关闭窗口会停止检查和下载。重新启动后，在队列中重试中断任务；软件不会在关闭后继续后台下载。网络断开或登录过期时仍可查看已缓存课程和本地视频，恢复网络并重新认证后即可更新。

## 视频与应用数据

所有课程视频保存在用户选择的同一根目录，下层按课程整理，默认目录为 macOS 的 `~/Movies/延河课堂`、Windows 的 `~/Videos/延河课堂`。

```text
视频根目录/
└── 2026-2027-1/
    └── 课程名称_课程ID/
        ├── 课时名称_课时ID_教师画面.mp4
        └── 课时名称_课时ID_PPT画面.mp4
```

| 系统 / 运行方式 | 登录会话、课程缓存与下载记录 |
| --- | --- |
| macOS 桌面版 | `~/Library/Application Support/YanhektDownloader/` |
| Windows 桌面版 | `%APPDATA%/YanhektDownloader/` |
| 网页版 | 项目内 `.state/` |

应用数据不放在安装目录，替换软件或升级不会覆盖历史记录。修改视频目录不会搬动之前的文件，原文件位置仍会保留在资料库中；移动或删除视频后点击扫描可更新状态。队列有待完成任务时，需要先完成或取消，才能修改保存目录。

`session.json` 包含可复用的登录会话，不要分享应用数据目录。需要清除登录状态时，退出软件后删除这个文件。卸载 Windows 软件会保留应用数据和视频。

从旧工具导入登录与任务记录（可选，保留原视频路径）：

```sh
# macOS，旧项目路径按实际修改；仅首次导入缺失的应用数据文件
"/Applications/延河课堂.app/Contents/MacOS/YanhektDownloader" --migrate-from "/path/to/old/project"
```

```powershell
# Windows
& "$env:LOCALAPPDATA\Programs\YanhektDownloader\YanhektDownloader.exe" --migrate-from "C:\path\to\old\project"
```

## 从源码运行

需要 Python 3.10+、FFmpeg 和本机图形桌面环境。FFmpeg 必须加入 `PATH`，macOS 可运行 `brew install ffmpeg`。

```sh
git clone https://github.com/Fangwenky/yanhekt-downloader.git
cd yanhekt-downloader
python3 -m venv .venv
.venv/bin/pip install -r requirements-desktop.txt
.venv/bin/playwright install --no-shell chromium
.venv/bin/python desktop.py
```

Windows PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m playwright install --no-shell chromium
.\.venv\Scripts\python.exe desktop.py
```

原本的本地网页版仍可使用 `./run.sh`，或安装 `requirements.txt` 和 Chromium 后运行 `python app.py`，地址为 <http://127.0.0.1:8765>。网页版支持 `--port 9000 --outdir /path/to/videos --concurrency 1 --no-open`，并发数可选 1–4。

## 构建桌面安装包

在目标系统上安装 `requirements-desktop.txt` 和 FFmpeg / ffprobe 后执行：

```sh
python build_desktop.py
```

脚本安装匹配的 Chromium 并使用 PyInstaller 打包，输出在 `dist/`。macOS 输出 `.app`，Windows 输出包含运行依赖的 `YanhektDownloader/` 文件夹，不能只复制其中一个 `.exe`。Windows 安装包通过 `packaging/windows.iss` 和 Inno Setup 6 构建；完整步骤见 [构建工作流](.github/workflows/build-desktop.yml)。GitHub Actions 分别在 macOS 和 Windows 构建，不做跨平台交叉打包。

## 常见问题

- **登录过期**：重新认证后检查登录，再拉取课程或重试下载。
- **跟踪后没有自动下载**：跟踪默认只检查更新；需要对这门课程单独开启自动下载，并选择合适的跟踪画面。
- **自动下载部分画面失败**：课程不一定提供 PPT / 学生画面，在跟踪设置中选择实际提供的画面；这些失败不影响其他任务。
- **显示回放但视频源已失效**：旧课时元数据可能还在，实际视频可能已被网站删除。可访问的视频才能下载。
- **续传**：MP4 需服务端支持 HTTP Range；HLS 使用 yt-dlp 分片记录续传，不支持时可能重新下载。
- **格式支持**：已验证 MP4 和单码率 HLS，多码率 HLS 主播放列表暂不支持。下载开始时通过官网播放器获取鉴权地址，HLS 分片通过官网 XHR 流程逐个获得鉴权参数。

## 仓库与验证

仓库只上传工具部分。`.gitignore` 排除 `download/`、`downloads/`、`.state/`、虚拟环境、音视频、下载分片、环境配置、日志、`build/`、`dist/` 和打包浏览器，任何用户登录、课程记录与录播都不上传。

```text
desktop.py / desktop.spec     原生窗口、用户数据与桌面打包
library.py                   课程跟踪、本地视频索引
app.py / yanhe.py            本地 API、下载队列、学校接口及播放器鉴权
web/                         课程、资料库和下载队列界面
packaging/                   Windows 安装向导
.github/workflows/           macOS / Windows 自动构建
```

```sh
python -m unittest -v test_app.py test_library.py
```

测试覆盖分页、回放解析、批量去重、取消重试、重启恢复、MP4 / HLS 下载、本地文件导入和缺失判断、新回放识别、跟踪与自动下载的区别、旧数据迁移。构建后执行打包程序的 `--smoke-test`，验证包内 Chromium 和 FFmpeg 可运行。学校接口已用实际 macOS 登录会话验证；Windows 构建环境验证不包含学校账号登录。

第三方组件说明见 [THIRD_PARTY.md](THIRD_PARTY.md)。
