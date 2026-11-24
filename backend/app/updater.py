"""Software updates for the desktop app (the "Start Here" install).

Flow: check GitHub for the newest commit on the release branch -> download that exact commit as a ZIP
-> verify it -> unpack it to data/updates/ and write pending.json -> ask the launcher to restart.
The launcher exits, `Start Here.bat` runs launcher/apply_update.py while nothing is running, which
swaps in the new code (keeping the data folder and installed packages), and starts the app again.

Standard library only. The data folder is never touched.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("OALGO_DATA_DIR") or ROOT / "data")
UPDATES = DATA / "updates"
CHECK_TTL = 30 * 60
MAX_ZIP = 300 * 1024 * 1024
REQUIRED = ("backend/pyproject.toml", "backend/uv.lock", "frontend/package.json", "launcher/launch.py", "launcher/apply_update.py")


class UpdateError(RuntimeError):
    pass


def enabled() -> bool:
    """Only for the desktop install. A git checkout (development) is never touched."""
    return os.environ.get("OALGO_DESKTOP") == "1" and not (ROOT / ".git").exists()


def config() -> dict[str, str]:
    cfg = {"repo": "vyomruppar/oalgo2", "branch": "main"}
    try:
        cfg.update(json.loads((ROOT / "launcher" / "update.json").read_text()))
    except (OSError, ValueError):
        pass
    cfg["api"] = os.environ.get("OALGO_UPDATE_API", "https://api.github.com").rstrip("/")
    cfg["zip"] = os.environ.get("OALGO_UPDATE_ZIP", "https://codeload.github.com").rstrip("/")
    return cfg


def installed() -> dict[str, Any] | None:
    try:
        return json.loads((DATA / "installed-version.json").read_text())
    except (OSError, ValueError):
        return None


def _open(url: str, timeout: float = 20.0):
    req = urllib.request.Request(url, headers={"User-Agent": "oalgo2-updater", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _get_json(url: str) -> Any:
    with _open(url) as r:
        return json.loads(r.read())


_cache: dict[str, Any] = {"at": 0.0, "value": None}
_lock = threading.Lock()


def check(force: bool = False) -> dict[str, Any]:
    """Compare the installed version with the newest commit on the release branch (cached 30 minutes)."""
    with _lock:
        if not force and _cache["value"] is not None and time.time() - _cache["at"] < CHECK_TTL:
            return _cache["value"]
    cur = installed()
    out: dict[str, Any] = {"installed_sha": (cur or {}).get("sha"), "installed_at": (cur or {}).get("applied_at"),
                           "latest_sha": None, "latest_message": None, "latest_date": None, "changes": [],
                           "update_available": False, "unknown_installed": cur is None,
                           "checked_at": datetime.now(timezone.utc).isoformat(), "error": None}
    cfg = config()
    try:
        c = _get_json(f"{cfg['api']}/repos/{cfg['repo']}/commits/{cfg['branch']}")
        out["latest_sha"] = c["sha"]
        out["latest_message"] = (c["commit"]["message"] or "").split("\n")[0]
        out["latest_date"] = (c["commit"].get("committer") or {}).get("date")
        out["update_available"] = c["sha"] != out["installed_sha"]
        if cur and out["update_available"]:
            try:
                cmp = _get_json(f"{cfg['api']}/repos/{cfg['repo']}/compare/{cur['sha']}...{c['sha']}")
                out["changes"] = [(x["commit"]["message"] or "").split("\n")[0] for x in cmp.get("commits", [])][-15:][::-1]
            except (urllib.error.URLError, OSError, KeyError, ValueError):
                pass
        if not out["changes"] and out["update_available"]:
            out["changes"] = [out["latest_message"]]
    except urllib.error.HTTPError as e:
        out["error"] = "GitHub is limiting requests right now. Try again in a few minutes." if e.code in (403, 429) else f"GitHub answered {e.code}."
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        out["error"] = "Could not reach GitHub. Check your internet connection."
    if out["error"] is None:
        with _lock:
            _cache.update(at=time.time(), value=out)
    return out


# ---- download and stage ---------------------------------------------------------------------------------
job: dict[str, Any] = {"state": "idle", "message": "", "percent": 0, "sha": None}


def _set(state: str, message: str = "", percent: int | None = None) -> None:
    job["state"], job["message"] = state, message
    if percent is not None:
        job["percent"] = percent


def _safe_extract(z: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    total = 0
    for info in z.infolist():
        target = (dest / info.filename).resolve()
        if dest != target and dest not in target.parents:
            raise UpdateError("The download contains an unsafe path and was rejected.")
        total += info.file_size
        if total > 3 * MAX_ZIP:
            raise UpdateError("The download is larger than expected and was rejected.")
    z.extractall(dest)


def stage(sha: str) -> Path:
    """Download and verify the exact commit, unpack it, and mark it pending. Returns the unpacked folder."""
    cfg = config()
    UPDATES.mkdir(parents=True, exist_ok=True)
    zip_path = UPDATES / f"{sha}.zip"
    new_dir = UPDATES / sha
    shutil.rmtree(new_dir, ignore_errors=True)
    _set("downloading", "Downloading the new version", 0)
    try:
        with _open(f"{cfg['zip']}/{cfg['repo']}/zip/{sha}", timeout=60) as r, open(zip_path, "wb") as f:
            size = int(r.headers.get("Content-Length") or 0)
            got = 0
            while chunk := r.read(256 * 1024):
                got += len(chunk)
                if got > MAX_ZIP:
                    raise UpdateError("The download is larger than expected and was rejected.")
                f.write(chunk)
                if size:
                    job["percent"] = min(90, int(90 * got / size))
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError("The download failed. Check your internet connection and try again.") from e
    _set("downloading", "Checking the download", 92)
    try:
        with zipfile.ZipFile(zip_path) as z:
            if (z.comment or b"").decode("ascii", "ignore").strip() != sha:
                raise UpdateError("The download is not the version that was announced and was rejected.")
            _safe_extract(z, new_dir)
    except zipfile.BadZipFile as e:
        raise UpdateError("The download was damaged. Try again.") from e
    roots = [p for p in new_dir.iterdir() if p.is_dir()]
    top = roots[0] if len(roots) == 1 and not any(p.is_file() for p in new_dir.iterdir()) else new_dir
    missing = [r for r in REQUIRED if not (top / r).exists()]
    if missing:
        raise UpdateError("The download is incomplete (" + ", ".join(missing[:2]) + " missing) and was rejected.")
    (UPDATES / "pending.json").write_text(json.dumps({"sha": sha, "dir": str(top.relative_to(UPDATES)), "staged_at": datetime.now(timezone.utc).isoformat()}))
    zip_path.unlink(missing_ok=True)
    _set("staged", "Ready to install", 100)
    return top


def request_restart() -> None:
    UPDATES.mkdir(parents=True, exist_ok=True)
    (UPDATES / "restart.flag").write_text(datetime.now(timezone.utc).isoformat())


def install(sha: str) -> None:
    """Background job for the Update button: stage the version, then ask the launcher to restart into it."""
    try:
        job["sha"] = sha
        stage(sha)
        _set("restarting", "Restarting to finish the update", 100)
        request_restart()
    except UpdateError as e:
        _set("error", str(e))
    except Exception as e:  # never leave the button spinning
        _set("error", f"The update could not be prepared ({type(e).__name__}).")


def start_install(sha: str) -> bool:
    if job["state"] in ("downloading", "restarting"):
        return False
    job.update(state="downloading", message="Starting", percent=0, sha=sha)
    threading.Thread(target=install, args=(sha,), daemon=True, name="update").start()
    return True


def reset_job() -> None:
    job.update(state="idle", message="", percent=0, sha=None)
