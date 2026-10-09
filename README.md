# 延河课堂录播下载工具

面向北京理工大学新版[延河课堂](https://aita.yanhekt.cn/education/?tenant_code=21#/home?menu_code=C-xswdkc,-1)的本地网页工具。通过北理统一认证后，自动获取个人课程列表，查看已有回放，并批量下载到电脑。

## 功能

| 功能 | 说明 |
| --- | --- |
| 统一认证登录 | 在独立 Chromium 窗口完成学校认证，使用认证页面提供的密码、短信或扫码等登录方式；工具不收集账号密码 |
| 自动拉取课程 | 分页获取账号“我的课程 / 全部课程”中的课程，支持课程名称、教师和学期筛选 |
| 查看已有回放 | 展示课程课时、教师及回放状态，未开始或尚未生成回放的课时不可勾选 |
| 批量下载 | 下载勾选的课时，或一次下载多门课程的全部已有回放 |
| 选择视频画面 | 支持教师、PPT、学生画面，按所选画面分别保存文件，实际可用画面取决于课程 |
| 下载队列 | 显示任务状态、进度、速度和预计剩余时间；默认同时运行 2 个任务 |
| 取消与重试 | 可取消任务、重试失败任务；支持下载器及服务端允许的断点续传 |
| 任务去重与恢复 | 跳过正在排队或已完成且文件仍存在的任务；重启后可重试中断任务 |
| 文件整理 | 按学期、课程、课时及视频画面保存，保存目录可在页面中修改 |

## 环境要求

- Python **3.10 或更高版本**。
- **FFmpeg**，安装后需要能在终端运行 `ffmpeg`。
- 能打开 Chromium 的本机桌面环境，以及访问延河课堂和北理统一认证网站的网络。
- 具有对应课程访问权限的北理账号。

当前已在 macOS 上验证。Linux、Windows 可使用下面的手动安装方式；Linux 登录需要图形桌面环境。

## 快速开始（macOS）

### 1. 获取源码

```sh
git clone https://github.com/Fangwenky/yanhekt-downloader.git
cd yanhekt-downloader
```

### 2. 安装 FFmpeg

已安装 Homebrew 的用户可运行：

```sh
brew install ffmpeg
```

确认 Python 和 FFmpeg 可用：

```sh
python3 --version
ffmpeg -version
```

### 3. 启动工具

```sh
./run.sh
```

首次启动会创建 `.venv/`，安装 Python 依赖及 Playwright Chromium，然后启动本地服务并打开浏览器：

**<http://127.0.0.1:8765>**

运行期间保留终端窗口。按 `Ctrl+C` 停止服务，下次运行 `./run.sh` 即可再次启动。

## 手动安装

先安装 Python 和 FFmpeg，并将 FFmpeg 加入系统 `PATH`。

### macOS / Linux

在项目目录执行：

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
.venv/bin/python app.py
```

Linux 若缺少 Chromium 系统依赖，可将浏览器安装步骤替换为：

```sh
.venv/bin/playwright install --with-deps chromium
```

### Windows（PowerShell）

在项目目录执行，无需激活虚拟环境：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe app.py
```

## 使用方法

1. **完成登录**：点击“统一认证登录”，在弹出的 Chromium 窗口中自行完成北理认证。回到工具页面点击“检查登录”；登录窗口打开后，工具也会定期检查登录状态。
2. **获取课程**：登录成功后会自动拉取课程。需要更新列表时点击“拉取课程”，可按课程、教师或学期筛选。
3. **选择画面**：在“下载画面”中勾选教师、PPT 或学生画面。每种画面对应一个独立的视频文件。
4. **选择下载内容**：点击左侧课程，勾选右侧已有回放，点击“下载所选回放”；或勾选左侧多门课程，点击“下载所选课程”，下载这些课程的全部已有回放。“全选当前列表”只选择当前筛选结果。
5. **查看下载**：切换“下载队列”，查看进度、取消任务或重试失败任务。点击“打开下载目录”查看文件。

保存目录可以在页面顶部修改并保存，下次启动时继续使用。队列中仍有待完成任务时，需先完成或取消任务才能修改目录；已有任务保留原来的文件路径。

## 启动参数

```sh
./run.sh --port 9000 --outdir "$HOME/Movies/yanhekt" --concurrency 2 --no-open
```

手动启动时将参数加在 `app.py` 后面：

```sh
.venv/bin/python app.py --port 9000 --concurrency 1
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--port` | `8765` | 本地网页服务端口 |
| `--outdir` | 上次保存的目录；首次为项目内 `downloads/` | 指定此次运行的下载目录 |
| `--concurrency` | `2` | 同时运行的下载任务数，可选 `1` 至 `4` |
| `--no-open` | 不启用 | 启动时不自动打开本地网页，仍可手动访问 |

## 文件保存结构

```text
downloads/
└── 2026-2027-1/
    └── 课程名称_课程ID/
        ├── 课时名称_课时ID_教师画面.mp4
        └── 课时名称_课时ID_PPT画面.mp4
```

课程 ID 和课时 ID 用于区分同名课程及回放。文件名中的非法路径字符会自动替换。

## 本地数据与 Git 忽略规则

仓库只包含工具源码、测试、依赖清单和使用文档。以下内容由 `.gitignore` 排除：

| 路径 / 类型 | 内容 |
| --- | --- |
| `download/`、`downloads/` | 本地课程录播和下载文件 |
| `.state/` | 登录会话、任务记录及保存目录配置 |
| `.venv/`、`venv/` | 本机 Python 虚拟环境 |
| `__pycache__/`、`*.py[cod]` | Python 编译缓存 |
| 常见视频、音频、`*.m3u8`、`*.part`、`*.ytdl` | 媒体文件、临时播放列表及下载中间文件 |
| `.env`、`.env.*`（保留 `.env.example`）、`*.log`、系统文件 | 本机环境配置、日志和系统元数据 |

`.state/session.json` 包含可复用的登录会话，**不要分享 `.state/` 目录**。需清除工具保存的登录状态时，先停止工具，再删除 `.state/session.json`。

服务只监听 `127.0.0.1`；写操作会校验本地来源和随机请求令牌。

## 常见问题

### 提示未检测到 FFmpeg

在启动工具的终端运行 `ffmpeg -version`。若命令不可用，请检查 FFmpeg 是否安装并加入 `PATH`，安装后重新打开终端并启动工具。

### 登录过期或课程拉取失败

点击“重新认证”，完成学校登录后点击“检查登录”，再拉取课程或重试下载。工具只获取当前账号有权限访问的个人课程。

### 某节课没有 PPT / 学生画面

不同课程可能只提供部分视频画面。未提供的画面会显示对应任务失败，不影响其他任务，可改选课程提供的画面。

### 页面显示已有回放，下载却失败或返回 404

旧课时的回放元数据可能仍存在，但实际视频源已删除或不可访问。网络问题或登录失效可重试；已经失效的视频源无法通过工具恢复。

### 中断后如何继续下载

重新启动工具，在“下载队列”中重试已取消或失败的任务。MP4 在服务端支持 HTTP Range 时可续传；HLS 使用 yt-dlp 分片记录续传，服务端不支持时可能重新下载。

### 工具支持哪些回放格式

支持已验证的 MP4 和单码率 HLS 播放列表，使用 yt-dlp 下载并通过 FFmpeg 整理为 MP4。多码率 HLS 主播放列表目前会提示暂不支持。

## 项目结构

```text
app.py            本地网页服务、下载队列及下载器
yanhe.py          统一认证会话、课程与回放 API、播放地址获取
web/              网页界面、样式和交互脚本
run.sh            macOS / Linux 启动脚本
requirements.txt  Python 依赖
test_app.py       解析、队列及下载测试
```

下载任务开始时使用官网播放器获取新的鉴权地址，HLS 分片也由官网的 XHR 流程逐个获取鉴权参数；临时播放列表会在下载结束后清理。

## 测试

安装依赖及 FFmpeg 后执行：

```sh
.venv/bin/python -m unittest -v test_app.py
```

测试覆盖嵌套课时解析、回放状态、课程分页、跨课程批量去重、取消与重试、任务恢复、MP4 / HLS 下载及输出文件。下载测试使用临时生成的本地视频，不需要学校账号。

新版网站接口已于 **2026-10-08** 使用实际登录会话验证。网站接口及播放鉴权方式变化后，工具可能需要相应更新。

相关项目与文档：[Playwright](https://playwright.dev/python/docs/auth)、[yt-dlp](https://github.com/yt-dlp/yt-dlp)、[FFmpeg](https://ffmpeg.org/)。
