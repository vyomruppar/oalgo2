import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

SHA_OLD, SHA_NEW = "a" * 40, "b" * 40
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def apply_mod():
    spec = importlib.util.spec_from_file_location("apply_update", REPO / "launcher" / "apply_update.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


OLD = {
    "Start Here.bat": "old bat", "README.md": "old readme", "Makefile": "old make",
    "backend/pyproject.toml": "old", "backend/uv.lock": "old", "backend/app/main.py": "old main", "backend/app/removed_module.py": "gone soon",
    "backend/.venv/lib/pkg.py": "installed packages", "frontend/node_modules/x/index.js": "deps", "frontend/.next/build.txt": "built",
    "frontend/package.json": "old pkg", "frontend/app/page.tsx": "old page", "frontend/app/old_route/page.tsx": "old route",
    "launcher/launch.py": "old launcher", "launcher/apply_update.py": "old apply", "docs/old.md": "old doc",
    "data/oalgo.sqlite": "MY HOLDINGS", "data/prices/MU.parquet": "prices", "data/installed-version.json": json.dumps({"sha": SHA_OLD}),
}
NEW = {
    "Start Here.bat": "NEW bat (must be ignored)", "README.md": "new readme", "Makefile": "new make",
    "backend/pyproject.toml": "new", "backend/uv.lock": "new", "backend/app/main.py": "new main", "backend/app/added.py": "added",
    "frontend/package.json": "new pkg", "frontend/app/page.tsx": "new page", "frontend/app/new_route/page.tsx": "new route",
    "launcher/launch.py": "new launcher", "launcher/apply_update.py": "new apply", "docs/new.md": "new doc",
    "data/oalgo.sqlite": "SHOULD NEVER BE WRITTEN", "frontend/node_modules/x/index.js": "SHOULD NOT REPLACE",
}


def stage_files(root: Path, files: dict[str, str] = NEW) -> None:
    new = root / "data" / "updates" / SHA_NEW / f"oalgo2-{SHA_NEW}"
    tree(new, files)
    (root / "data" / "updates" / "pending.json").write_text(json.dumps({"sha": SHA_NEW, "dir": f"{SHA_NEW}/oalgo2-{SHA_NEW}"}))


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file() and "updates" not in p.parts}


def test_apply_replaces_program_files_and_keeps_data_and_packages(tmp_path, apply_mod):
    tree(tmp_path, OLD)
    stage_files(tmp_path)
    assert apply_mod.apply(tmp_path) == 0
    now = snapshot(tmp_path)
    assert now["backend/app/main.py"] == "new main" and now["backend/app/added.py"] == "added"
    assert "backend/app/removed_module.py" not in now                       # deleted upstream, deleted here
    assert "frontend/app/old_route/page.tsx" not in now and now["frontend/app/new_route/page.tsx"] == "new route"
    assert now["launcher/launch.py"] == "new launcher" and now["docs/new.md"] == "new doc" and "docs/old.md" not in now
    assert now["Start Here.bat"] == "old bat"                               # the running file is never replaced
    assert now["data/oalgo.sqlite"] == "MY HOLDINGS" and now["data/prices/MU.parquet"] == "prices"
    assert now["backend/.venv/lib/pkg.py"] == "installed packages" and now["frontend/node_modules/x/index.js"] == "deps"
    assert now["frontend/.next/build.txt"] == "built"
    v = json.loads(now["data/installed-version.json"])
    assert v["sha"] == SHA_NEW and v["previous_sha"] == SHA_OLD
    assert (tmp_path / "data/updates/just-applied.json").exists() and not (tmp_path / "data/updates/pending.json").exists()


def test_rollback_restores_every_file_exactly(tmp_path, apply_mod):
    tree(tmp_path, OLD)
    before = snapshot(tmp_path)
    stage_files(tmp_path)
    apply_mod.apply(tmp_path)
    assert snapshot(tmp_path) != before
    assert apply_mod.restore(tmp_path) == 0
    assert snapshot(tmp_path) == before                                      # byte-for-byte, nothing added, nothing missing
    assert not (tmp_path / "data/updates/just-applied.json").exists()
    assert json.loads((tmp_path / "data/installed-version.json").read_text())["sha"] == SHA_OLD


def test_failed_install_leaves_the_old_version_untouched(tmp_path, apply_mod, monkeypatch):
    tree(tmp_path, OLD)
    before = snapshot(tmp_path)
    stage_files(tmp_path)
    real_put, calls = apply_mod.put, {"n": 0}

    def flaky(src, dst):
        if str(src).startswith(str(tmp_path / "data/updates" / SHA_NEW)):
            calls["n"] += 1
            if calls["n"] == 4:
                raise OSError("disk full")
        return real_put(src, dst)

    monkeypatch.setattr(apply_mod, "put", flaky)
    assert apply_mod.apply(tmp_path) == 1
    assert snapshot(tmp_path) == before
    assert not (tmp_path / "data/updates/pending.json").exists()


def test_rollback_without_a_backup_is_harmless(tmp_path, apply_mod):
    tree(tmp_path, OLD)
    assert apply_mod.restore(tmp_path) == 1
    assert snapshot(tmp_path) == snapshot(tmp_path)


# ---- check / download / stage ------------------------------------------------------------------------------
@pytest.fixture()
def upd(tmp_path, monkeypatch):
    monkeypatch.setenv("OALGO_DESKTOP", "1")
    monkeypatch.setenv("OALGO_DATA_DIR", str(tmp_path / "data"))
    from app import updater
    monkeypatch.setattr(updater, "ROOT", tmp_path)
    monkeypatch.setattr(updater, "DATA", tmp_path / "data")
    monkeypatch.setattr(updater, "UPDATES", tmp_path / "data" / "updates")
    updater._cache.update(at=0.0, value=None)
    updater.reset_job()
    (tmp_path / "launcher").mkdir()
    (tmp_path / "launcher" / "update.json").write_text(json.dumps({"repo": "me/oalgo2", "branch": "release"}))
    return updater


def make_zip(files: dict[str, str], comment: str = SHA_NEW, prefix: str = f"oalgo2-{SHA_NEW}/") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for rel, text in files.items():
            z.writestr(prefix + rel, text)
        z.comment = comment.encode()
    return buf.getvalue()


class Resp(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


REQUIRED_FILES = {r: "x" for r in ("backend/pyproject.toml", "backend/uv.lock", "frontend/package.json", "launcher/launch.py", "launcher/apply_update.py")}


def test_disabled_outside_the_desktop_install(tmp_path, monkeypatch):
    from app import updater
    monkeypatch.delenv("OALGO_DESKTOP", raising=False)
    assert updater.enabled() is False
    monkeypatch.setenv("OALGO_DESKTOP", "1")
    monkeypatch.setattr(updater, "ROOT", REPO)          # the development checkout has a .git folder
    assert updater.enabled() is False


def test_check_reports_changes_and_caches(upd, monkeypatch):
    (upd.DATA).mkdir(parents=True)
    (upd.DATA / "installed-version.json").write_text(json.dumps({"sha": SHA_OLD, "applied_at": "2026-11-01T00:00:00Z"}))
    calls = []

    def fake(url):
        calls.append(url)
        if "/commits/release" in url:
            return {"sha": SHA_NEW, "commit": {"message": "Add live quotes\n\nbody", "committer": {"date": "2026-11-24T12:00:00Z"}}}
        return {"commits": [{"commit": {"message": "first change"}}, {"commit": {"message": "second change"}}]}

    monkeypatch.setattr(upd, "_get_json", fake)
    s = upd.check()
    assert s["update_available"] and s["latest_sha"] == SHA_NEW and s["latest_message"] == "Add live quotes"
    assert s["changes"] == ["second change", "first change"] and not s["unknown_installed"]
    assert any("compare/" + SHA_OLD in c for c in calls)
    n = len(calls)
    upd.check()
    assert len(calls) == n                                                    # cached for 30 minutes
    (upd.DATA / "installed-version.json").write_text(json.dumps({"sha": SHA_NEW}))
    assert upd.check(force=True)["update_available"] is False


def test_check_is_honest_about_failures(upd, monkeypatch):
    import urllib.error

    def boom(url):
        raise urllib.error.HTTPError(url, 403, "rate limited", {}, None)

    monkeypatch.setattr(upd, "_get_json", boom)
    s = upd.check()
    assert s["update_available"] is False and "limiting" in s["error"]
    assert upd._cache["value"] is None                                         # a failure is not cached


def test_stage_verifies_unpacks_and_marks_pending(upd, monkeypatch):
    monkeypatch.setattr(upd, "_open", lambda url, timeout=0: Resp(make_zip(REQUIRED_FILES)))
    top = upd.stage(SHA_NEW)
    assert (top / "launcher/launch.py").exists()
    p = json.loads((upd.UPDATES / "pending.json").read_text())
    assert p["sha"] == SHA_NEW and (upd.UPDATES / p["dir"] / "backend/pyproject.toml").exists()
    assert upd.job["state"] == "staged"


@pytest.mark.parametrize("zipbytes,msg", [
    (make_zip(REQUIRED_FILES, comment="c" * 40), "not the version"),
    (make_zip({k: v for k, v in REQUIRED_FILES.items() if k != "backend/uv.lock"}), "incomplete"),
    (make_zip({**REQUIRED_FILES, "../evil.txt": "x"}, prefix=""), "unsafe path"),
    (b"not a zip at all", "damaged"),
])
def test_stage_rejects_bad_downloads(upd, monkeypatch, zipbytes, msg):
    monkeypatch.setattr(upd, "_open", lambda url, timeout=0: Resp(zipbytes))
    with pytest.raises(upd.UpdateError, match=msg):
        upd.stage(SHA_NEW)
    assert not (upd.UPDATES / "pending.json").exists()


def test_install_job_stages_then_requests_restart_and_reports_errors(upd, monkeypatch):
    monkeypatch.setattr(upd, "_open", lambda url, timeout=0: Resp(make_zip(REQUIRED_FILES)))
    upd.install(SHA_NEW)
    assert upd.job["state"] == "restarting" and (upd.UPDATES / "restart.flag").exists()
    (upd.UPDATES / "restart.flag").unlink()
    upd.reset_job()
    monkeypatch.setattr(upd, "_open", lambda url, timeout=0: Resp(b"junk"))
    upd.install(SHA_NEW)
    assert upd.job["state"] == "error" and "damaged" in upd.job["message"] and not (upd.UPDATES / "restart.flag").exists()


def test_update_endpoints(upd, monkeypatch, tmp_env):
    from fastapi.testclient import TestClient
    from app.api.main import app
    from app.jobs import pipeline
    monkeypatch.setattr(upd, "check", lambda force=False: {"update_available": True, "latest_sha": SHA_NEW, "installed_sha": SHA_OLD, "error": None, "changes": ["x"]})
    started = []
    monkeypatch.setattr(upd, "start_install", lambda sha: started.append(sha) or True)
    with TestClient(app) as c:
        s = c.get("/api/update/status").json()
        assert s["enabled"] and s["update_available"] and s["scan_running"] is False
        assert c.post("/api/update/install").status_code == 202 and started == [SHA_NEW]
        monkeypatch.setattr(pipeline, "is_running", lambda: True)
        assert c.post("/api/update/install").status_code == 409                    # never interrupt a scan
        monkeypatch.setattr(pipeline, "is_running", lambda: False)
        monkeypatch.setattr(upd, "check", lambda force=False: {"update_available": False, "latest_sha": SHA_OLD, "error": None})
        assert c.post("/api/update/install").status_code == 409
        monkeypatch.setattr(upd, "check", lambda force=False: {"error": "Could not reach GitHub."})
        assert c.post("/api/update/install").status_code == 502
        monkeypatch.setenv("OALGO_DESKTOP", "0")
        assert c.get("/api/update/status").json() == {"enabled": False}
        assert c.post("/api/update/install").status_code == 400
