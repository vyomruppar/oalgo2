"""Applies a downloaded oalgo2 update, or undoes it. Run by "Start Here.bat" while oalgo2 is NOT running.

    python apply_update.py <oalgo2 folder>            install the pending update
    python apply_update.py <oalgo2 folder> rollback   restore the version that was replaced

Replaces program files only. The data folder, installed packages and the built dashboard are kept
(the dashboard is rebuilt automatically when its source changed). "Start Here.bat" is never replaced:
it is the file that is running this script. A copy of every replaced item is kept in data/updates/backup
so the previous version can be restored.

Standard library only, so it runs with any Python and never depends on the packages being updated.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

NEVER_TOUCH = {".git", "data", "Start Here.bat"}
KEEP_INSIDE = {"backend": {".venv", "data", ".env", "__pycache__", ".pytest_cache", ".ruff_cache"},
               "frontend": {"node_modules", ".next", ".vercel", ".env", ".env.local", "snapshot", "tsconfig.tsbuildinfo"}}


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def targets(new_root: Path) -> list[str]:
    """Relative paths (posix) of everything the update replaces."""
    out: list[str] = []
    for top in sorted(new_root.iterdir()):
        if top.name in NEVER_TOUCH:
            continue
        if top.name in KEEP_INSIDE and top.is_dir():
            for child in sorted(top.iterdir()):
                if child.name not in KEEP_INSIDE[top.name]:
                    out.append(f"{top.name}/{child.name}")
        else:
            out.append(top.name)
    return out


def remove(p: Path) -> None:
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    elif p.exists() or p.is_symlink():
        p.unlink()


def put(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def apply(root: Path) -> int:
    updates = root / "data" / "updates"
    pending = updates / "pending.json"
    if not pending.exists():
        return 0
    info = json.loads(pending.read_text())
    new_root = (updates / info["dir"]).resolve()
    if updates.resolve() not in new_root.parents or not (new_root / "launcher" / "launch.py").exists():
        log("The downloaded update is missing or damaged. Skipping it.")
        pending.unlink(missing_ok=True)
        return 0
    backup = updates / "backup"
    shutil.rmtree(backup, ignore_errors=True)
    backup.mkdir(parents=True)
    items = targets(new_root)
    replaced: list[dict] = []
    log(f"Installing the update ({len(items)} items). Your data is not touched.")
    try:
        for rel in items:
            old, new = root / rel, new_root / rel
            existed = old.exists() or old.is_symlink()
            if existed:
                put(old, backup / rel)
            replaced.append({"path": rel, "existed": existed})
            remove(old)
            put(new, old)
        previous, previous_text = None, None
        vf = root / "data" / "installed-version.json"
        if vf.exists():
            previous_text = vf.read_text()
            previous = json.loads(previous_text).get("sha")
        (backup / "manifest.json").write_text(json.dumps({"replaced": replaced, "previous_sha": previous, "previous_version_file": previous_text,
                                                          "new_sha": info["sha"]}))
        vf.write_text(json.dumps({"sha": info["sha"], "applied_at": datetime.now(timezone.utc).isoformat(), "previous_sha": previous}))
        (updates / "just-applied.json").write_text(json.dumps({"sha": info["sha"], "previous_sha": previous}))
    except Exception as e:  # put everything back rather than leave a half-updated install
        log(f"The update could not be installed ({type(e).__name__}: {e}). Restoring the previous version.")
        (backup / "manifest.json").write_text(json.dumps({"replaced": replaced, "previous_sha": None, "previous_version_file": None, "new_sha": None}))
        restore(root, quiet=True)
        pending.unlink(missing_ok=True)
        return 1
    pending.unlink(missing_ok=True)
    shutil.rmtree(updates / info["sha"], ignore_errors=True)
    (updates / "restart.flag").unlink(missing_ok=True)
    log("Update installed. Starting the new version.")
    return 0


def restore(root: Path, quiet: bool = False) -> int:
    updates = root / "data" / "updates"
    backup = updates / "backup"
    mf = backup / "manifest.json"
    if not mf.exists():
        if not quiet:
            log("There is no earlier version to go back to.")
        return 1
    m = json.loads(mf.read_text())
    for item in reversed(m["replaced"]):
        cur = root / item["path"]
        remove(cur)
        if item["existed"]:
            put(backup / item["path"], cur)
    vf = root / "data" / "installed-version.json"
    if m.get("previous_version_file") is not None:
        vf.write_text(m["previous_version_file"])      # exactly as it was
    elif m.get("new_sha") and vf.exists():
        vf.unlink()                                   # there was no version record before the update
    if m.get("new_sha") and not quiet:
        (updates / "rolled-back.json").write_text(json.dumps({"sha": m["new_sha"], "at": datetime.now(timezone.utc).isoformat()}))
    (updates / "just-applied.json").unlink(missing_ok=True)
    (updates / "restart.flag").unlink(missing_ok=True)
    if not quiet:
        log("Went back to the previous version.")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: apply_update.py <oalgo2 folder> [rollback]")
        return 2
    root = Path(sys.argv[1]).resolve()
    if len(sys.argv) > 2 and sys.argv[2] == "rollback":
        return restore(root)
    return apply(root)


if __name__ == "__main__":
    sys.exit(main())
