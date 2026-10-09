# Third-party components

The desktop package includes the following open-source components. Each component retains its own license; this project does not change those licenses.

- Python — Python Software Foundation License: https://docs.python.org/3/license.html
- pywebview — BSD 3-Clause: https://github.com/r0x0r/pywebview/blob/master/LICENSE
- Playwright — Apache 2.0: https://github.com/microsoft/playwright-python/blob/main/LICENSE
- Chromium — BSD and bundled component licenses: https://chromium.googlesource.com/chromium/src/+/main/LICENSE . Chromium's license and credits resources are included in the browser directory.
- yt-dlp — Unlicense; bundled dependencies have their own licenses: https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE
- PyInstaller — GPL with a distribution exception for generated applications: https://pyinstaller.org/en/stable/license.html
- FFmpeg / ffprobe — build-dependent LGPL or GPL: https://ffmpeg.org/legal.html . The distributed builds enable GPL components. Corresponding source and build recipes: https://github.com/FFmpeg/FFmpeg (version tags), https://github.com/Homebrew/homebrew-core/tree/HEAD/Formula/f (macOS build), https://github.com/GyanD/codexffmpeg (Windows build and linked libraries). The FFmpeg build configuration can be inspected with the bundled `ffmpeg -version` command. These components are independent executable programs invoked as subprocesses.
- Windows: pythonnet (MIT), https://github.com/pythonnet/pythonnet/blob/master/LICENSE ; Microsoft Edge WebView2 Runtime is a system dependency with Microsoft's terms, https://developer.microsoft.com/microsoft-edge/webview2/ . The installer uses Microsoft's official Evergreen bootstrapper if that runtime is absent.

The desktop build contains public program files only. It never includes a user's login session, course database, video downloads, or account details.
