import os
import sys
import json
import time
import urllib.request
import urllib.error
import tempfile
import subprocess
import logging
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
APP_DATA = Path(os.getenv('APPDATA', str(Path.home()))) / "YTDownloader"
APP_DATA.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(APP_DATA / "service.log"),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GITHUB_API_RELEASES_LATEST = "https://api.github.com/repos/{owner}/{repo}/releases/latest"


def _read_local_version() -> str:
    if getattr(sys, 'frozen', False):
        vfile = Path(sys.executable).resolve().parent / "VERSION"
    else:
        vfile = APP_DIR / "VERSION"
    try:
        return vfile.read_text(encoding='utf-8').strip()
    except Exception:
        return "0.0.0"


def _parse_version(v: str):
    # Very lightweight parser: split on non-digits and compare numeric parts
    parts = []
    for token in v.strip().split("."):
        try:
            parts.append(int(token))
        except Exception:
            # Strip any leading non-digit characters (e.g. v1.2.3)
            digits = ''.join(ch for ch in token if ch.isdigit())
            parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _is_newer(local: str, remote: str) -> bool:
    return _parse_version(remote) > _parse_version(local)


def _http_get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "YTDownloader-Updater"})
    # Fail fast (5s) so the app doesn't hang on startup if offline
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def _download_url_to(path: Path, url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "YTDownloader-Updater"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    path.write_bytes(data)


def _choose_installer_asset(release_json: dict) -> dict:
    # Prefer a Windows installer (exe) named like Setup, Installer, or containing YTService
    assets = release_json.get('assets', [])
    if not assets:
        return None

    # helper to score assets
    def score(a: dict):
        name = (a.get('name') or '').lower()
        if name.endswith('.exe'):
            if 'setup' in name or 'installer' in name or 'yt' in name or 'service' in name:
                return 100
            return 80
        if name.endswith('.zip'):
            return 50
        return 0

    best = max(assets, key=score)
    return best if score(best) > 0 else None


def check_for_update_and_install(owner: str = 'kishtalaw', repo: str = 'yt-downloader', auto_install: bool = True) -> bool:
    """Check GitHub latest release for a newer version. If newer and auto_install True,
    download the best installer asset and run it (silent). Returns True if installer started.
    """
    if os.name != 'nt':
        logger.info("Auto-update: not running on Windows, skipping")
        return False

    local_v = _read_local_version()
    url = GITHUB_API_RELEASES_LATEST.format(owner=owner, repo=repo)
    logger.info("Checking for updates on %s", url)
    try:
        release = _http_get_json(url)
    except urllib.error.HTTPError as e:
        logger.warning("Update check failed: %s", e)
        return False
    except Exception as e:
        logger.exception("Update check failed: %s", e)
        return False

    # Release tag or name
    remote_v = (release.get('tag_name') or release.get('name') or '').lstrip('vV')
    if not remote_v:
        logger.info("No version tag/name found on release, skipping")
        return False

    logger.info("Local version %s, remote version %s", local_v, remote_v)
    try:
        if not _is_newer(local_v, remote_v):
            logger.info("No update available")
            return False
    except Exception:
        # If parsing fails, only proceed if versions differ
        if local_v == remote_v:
            return False

    asset = _choose_installer_asset(release)
    if not asset:
        logger.info("No suitable installer asset found in release %s", remote_v)
        return False

    download_url = asset.get('browser_download_url')
    if not download_url:
        logger.info("Asset has no download URL")
        return False

    # Download to temp
    tmp_dir = Path(tempfile.gettempdir())
    filename = asset.get('name')
    out_path = tmp_dir / filename
    logger.info("Downloading update asset %s -> %s", download_url, out_path)
    try:
        _download_url_to(out_path, download_url)
    except Exception as e:
        logger.exception("Failed to download update: %s", e)
        return False

    if not auto_install:
        logger.info("Auto-install disabled; update downloaded to %s", out_path)
        return True

    # Run installer silently
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
    try:
        # Inno Setup supports /VERYSILENT /NORESTART. Let the installer request elevation if required.
        logger.info("Launching installer %s", out_path)
        subprocess.Popen([str(out_path), "/VERYSILENT", "/NORESTART"], creationflags=flags)
        logger.info("Installer started")
        return True
    except Exception:
        logger.exception("Failed to start installer")
        return False


if __name__ == '__main__':
    # Simple local test runner
    res = check_for_update_and_install(auto_install=False)
    print('check_for_update_and_install returned', res)
