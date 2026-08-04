"""Zero-touch update checker for laptop users with no git installed.

Called from START_WEB.bat / START_STREAMLIT.bat before the server starts. Compares the
local installed version (data/.update_state.json) against version.json on GitHub's main
branch. If newer, downloads the repo ZIP, verifies it, and copies only known CODE paths
over the local install — .env, data/, output/, .venv/, and built frontend assets are never
touched because they are simply not on the copy allow-list below.

Must never block app startup: any network failure, timeout, or corrupt download is caught,
logged, and the script exits 0 so the calling .bat continues straight to starting the app.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO_OWNER = "namancoherent-web"
REPO_NAME = "vendor-intelligence"
BRANCH = "main"

RAW_VERSION_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/version.json"
ZIP_URL = f"https://codeload.github.com/{REPO_OWNER}/{REPO_NAME}/zip/refs/heads/{BRANCH}"

# Only these top-level paths are ever copied from a downloaded update. Anything not listed
# here (.env, data/, output/, .venv/, frontend/node_modules, frontend/out) is never touched,
# regardless of what the downloaded ZIP contains.
CODE_ALLOWLIST = [
    "src",
    "api",
    "backend",
    "ui",
    "scripts",
    "config",
    "crawler",
    "frontend/src",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/next.config.js",
    "frontend/tsconfig.json",
    "frontend/next-env.d.ts",
    "app.py",
    "requirements.txt",
    "version.json",
    "START_WEB.bat",
    "START_STREAMLIT.bat",
    "setup_local.bat",
    "setup.bat",
    "run.bat",
]

REQUEST_TIMEOUT_SECONDS = 8
CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # once per day


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _state_path() -> Path:
    return _project_root() / "data" / ".update_state.json"


def _load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    p = _state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass  # non-fatal — worst case we re-check next launch


def _local_version() -> str:
    p = _project_root() / "version.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def _fetch_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [update] version check skipped (no connection or GitHub unreachable): {exc}")
        return None


def _version_tuple(v: str) -> tuple[int, ...]:
    parts = []
    for chunk in str(v or "0").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


SERVER_PORTS = (8080, 8501)  # api/main.py (uvicorn) and app.py (streamlit)


def _is_locked() -> bool:
    """True if this app's own server is already listening — checked directly via the actual
    port instead of a lock FILE, which would go stale forever if a previous window was closed
    uncleanly (e.g. the X button) instead of stopped normally."""
    import socket

    for port in SERVER_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        except Exception:
            pass
        finally:
            s.close()
    return False


def _download_zip(dest_dir: Path) -> Path | None:
    zip_path = dest_dir / "update.zip"
    try:
        req = urllib.request.Request(ZIP_URL)
        with urllib.request.urlopen(req, timeout=60) as resp, open(zip_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        return zip_path
    except Exception as exc:
        print(f"  [update] download failed, skipping this update: {exc}")
        return None


def _verify_and_extract(zip_path: Path, extract_to: Path) -> Path | None:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            if bad:
                print(f"  [update] downloaded archive is corrupt (bad entry: {bad}), aborting")
                return None
            zf.extractall(extract_to)
    except Exception as exc:
        print(f"  [update] could not open downloaded archive, aborting: {exc}")
        return None

    # GitHub ZIPs extract into a single "<repo>-<branch>" subfolder
    candidates = [d for d in extract_to.iterdir() if d.is_dir()]
    if not candidates:
        print("  [update] downloaded archive was empty, aborting")
        return None
    root = candidates[0]

    required = ["version.json", "requirements.txt", "api/main.py"]
    for rel in required:
        if not (root / rel).exists():
            print(f"  [update] downloaded archive missing expected file {rel!r}, aborting")
            return None
    return root


def _copy_allowlisted(src_root: Path, dest_root: Path) -> None:
    for rel in CODE_ALLOWLIST:
        src = src_root / rel
        dest = dest_root / rel
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def _backup_allowlisted(dest_root: Path, backup_root: Path) -> None:
    for rel in CODE_ALLOWLIST:
        src = dest_root / rel
        if not src.exists():
            continue
        dst = backup_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def run_check(force: bool = False) -> None:
    project_root = _project_root()

    if _is_locked():
        print("  [update] server appears to be running elsewhere, skipping update check")
        return

    state = _load_state()
    last_check = float(state.get("last_check_epoch") or 0)
    if not force and (time.time() - last_check) < CHECK_INTERVAL_SECONDS:
        return  # checked recently, don't hit the network every single launch

    state["last_check_epoch"] = time.time()
    _save_state(state)  # write before the network call so a hang never re-triggers next launch

    remote = _fetch_json(RAW_VERSION_URL)
    if not remote:
        return

    local_v = _local_version()
    remote_v = str(remote.get("version") or "0.0.0")
    if _version_tuple(remote_v) <= _version_tuple(local_v):
        return  # up to date

    print(f"  [update] newer version available: {local_v} -> {remote_v}. Updating...")

    with tempfile.TemporaryDirectory(prefix="vi_update_") as tmp:
        tmp_path = Path(tmp)
        zip_path = _download_zip(tmp_path)
        if not zip_path:
            return
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        new_root = _verify_and_extract(zip_path, extract_dir)
        if not new_root:
            return

        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        try:
            _backup_allowlisted(project_root, backup_dir)
            _copy_allowlisted(new_root, project_root)
        except Exception as exc:
            print(f"  [update] update failed midway ({exc}), restoring previous files...")
            try:
                _copy_allowlisted(backup_dir, project_root)
                print("  [update] restore complete, continuing with previous version")
            except Exception as restore_exc:
                print(f"  [update] restore ALSO failed ({restore_exc}) - please re-download the repo ZIP manually")
            return

        if remote.get("requirements_changed"):
            deps_marker = project_root / ".venv" / ".deps_ok"
            try:
                deps_marker.unlink(missing_ok=True)
                print("  [update] dependencies changed - will reinstall packages this run")
            except Exception:
                pass

        if remote.get("frontend_changed"):
            frontend_out = project_root / "frontend" / "out"
            try:
                if frontend_out.exists():
                    shutil.rmtree(frontend_out)
                print(
                    "  [update] frontend changed - Web UI will rebuild automatically "
                    "on the NEXT launch of START_WEB.bat (needs Node/npm)"
                )
            except Exception:
                pass

        print(f"  [update] updated successfully to version {remote_v}")


if __name__ == "__main__":
    try:
        run_check(force="--force" in sys.argv)
    except Exception as exc:
        # Absolute last-resort guard: an update check must NEVER prevent the app from starting.
        print(f"  [update] update check failed unexpectedly, continuing anyway: {exc}")
    sys.exit(0)
