# Native build only: Python, UI, Chromium and FFmpeg; no local user data.
import os
import shutil
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH)
browsers = root / '.build-browsers'
if not browsers.is_dir():
    raise RuntimeError('Run build_desktop.py to install the bundled browser first')
binaries = []
for program in ('ffmpeg', 'ffprobe'):
    location = shutil.which(program)
    if not location:
        raise RuntimeError(program + ' is required for packaging')
    binaries.append((str(Path(location).resolve()), 'bin'))
datas = [(str(root / 'web'), 'web'),
         (str(root / 'THIRD_PARTY.md'), '.'), (str(root / 'README.md'), '.')]
datas += collect_data_files('webview')
a = Analysis([str(root / 'desktop.py')], pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=collect_submodules('yt_dlp') + ['webview.platforms.cocoa' if sys.platform == 'darwin' else 'webview.platforms.winforms'],
    excludes=['tkinter', 'pytest', 'IPython'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='YanhektDownloader',
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='YanhektDownloader')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='延河课堂.app', bundle_identifier='cn.yanhekt.downloader',
        info_plist={'CFBundleShortVersionString':'0.2.0', 'NSHighResolutionCapable':True,
                    'NSAppTransportSecurity':{'NSAllowsLocalNetworking':True}})
