"""Build on the target OS; no cross-compilation or personal data inclusion."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(root / '.build-browsers'))
subprocess.run([sys.executable, '-m', 'playwright', 'install', '--no-shell', 'chromium'], env=env, cwd=root, check=True)
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', 'desktop.spec'], env=env, cwd=root, check=True)
# Keep Chromium's own framework paths and signatures intact. PyInstaller must
# not rewrite this separately bundled application's Mach-O dependencies.
if sys.platform == 'darwin':
    package = root / 'dist/延河课堂.app'
    destination = package / 'Contents/Resources/browsers'
else:
    destination = root / 'dist/YanhektDownloader/_internal/browsers'
shutil.copytree(root / '.build-browsers', destination, symlinks=True, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('.links'))
if sys.platform == 'darwin':
    (package / 'Contents/Frameworks/browsers').symlink_to('../Resources/browsers')
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(package)], check=True)
