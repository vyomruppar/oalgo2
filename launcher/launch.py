"""oalgo2 desktop launcher, started by "Start Here.bat" (or directly with Python).

Builds the dashboard the first time (and after an update), starts the research engine and the
dashboard on this computer only (127.0.0.1), runs a catch-up scan if the data is old, and opens the
dashboard in its own window. Closing that window stops everything.

Standard library only: it runs inside the backend's Python environment, which `uv` creates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DATA = ROOT / "data"
LOGS = DATA / "logs"
API_PORT = 8765
UI_PORT = 3765
API = f"http://127.0.0.1:{API_PORT}"
UI = f"http://127.0.0.1:{UI_PORT}"
PNPM = "pnpm@10.28.0"
IS_WIN = os.name == "nt"


def say(msg: str) -> None:
    print(f"  {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"\n  Could not start oalgo2: {msg}\n", flush=True)
    sys.exit(1)


# ---- Node (bundled through the nodejs-wheel-binaries Python package) ----------------------------------
def node_paths() -> tuple[Path, Path]:
    try:
        import nodejs_wheel
    except ImportError:
        fail("the bundled Node.js is missing. Start oalgo2 with 'Start Here.bat', which installs it.")
    root = Path(nodejs_wheel.__file__).parent
    node = root / ("node.exe" if IS_WIN else "bin/node")
    npx_cli = root / "lib" / "node_modules" / "npm" / "bin" / "npx-cli.js"
    if not node.exists() or not npx_cli.exists():
        fail(f"the bundled Node.js is incomplete ({root}). Delete the backend\\.venv folder and start again.")
    return node, npx_cli


def node_env(node: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env["BACKEND_URL"] = API
    env.pop("APP_PASSWORD", None)  # no sign-in on your own computer
    for k in ("NEXT_PUBLIC_SNAPSHOT", "NEXT_PUBLIC_QUEUE"):
        env.pop(k, None)
    return env


# ---- Dashboard build ------------------------------------------------------------------------------------
SKIP_DIRS = {"node_modules", ".next", ".vercel", "out", "snapshot", "test-results", "playwright-report"}


def fingerprint() -> str:
    """Changes whenever the dashboard's source, lockfile or backend address changes."""
    h = hashlib.sha256(f"backend={API}".encode())
    for dirpath, dirnames, filenames in os.walk(FRONTEND):
        rel = Path(dirpath).relative_to(FRONTEND)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not (rel == Path("public") and d == "data"))
        for f in sorted(filenames):
            if f.endswith(".tsbuildinfo") or f.startswith(".env"):
                continue
            p = Path(dirpath) / f
            h.update(str(p.relative_to(FRONTEND)).replace("\\", "/").encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def build_dashboard(node: Path, npx_cli: Path) -> None:
    stamp = FRONTEND / ".next" / "oalgo-build.txt"
    want = fingerprint()
    if stamp.exists() and stamp.read_text().strip() == want:
        return
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / "dashboard-build.log"
    first = not (FRONTEND / "node_modules").exists()
    say("Setting up the dashboard" + (" (first start only, about 3 to 5 minutes)." if first else " after an update (about 2 minutes)."))
    env = node_env(node)
    with open(log, "w", encoding="utf-8") as out:
        for step in (["install", "--frozen-lockfile"], ["build"]):
            r = subprocess.run([str(node), str(npx_cli), "--yes", PNPM, *step], cwd=FRONTEND, env=env, stdout=out, stderr=subprocess.STDOUT)
            if r.returncode != 0:
                fail(f"setting up the dashboard failed during 'pnpm {step[0]}'. Details: {log}")
    stamp.write_text(want)


# ---- Servers --------------------------------------------------------------------------------------------
def up(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except (urllib.error.URLError, OSError):
        return False


def ours(timeout: float = 8.0) -> bool:
    """True if the program answering on the research engine's port is oalgo2 (it may be busy scanning)."""
    try:
        with urllib.request.urlopen(f"{API}/api/health", timeout=timeout) as r:
            return "No real orders" in r.read().decode()
    except (urllib.error.URLError, OSError, ValueError):
        return False


def listening(port: int) -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def start(cmd: list[str], cwd: Path, env: dict[str, str], log_name: str) -> subprocess.Popen:
    LOGS.mkdir(parents=True, exist_ok=True)
    out = open(LOGS / log_name, "a", encoding="utf-8")
    out.write(f"\n---- started {datetime.now().isoformat(timespec='seconds')} ----\n")
    out.flush()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0
    return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, creationflags=flags,
                            start_new_session=not IS_WIN)


def wait_for(url: str, proc: subprocess.Popen, what: str, log_name: str, timeout: float = 180) -> None:
    t = time.time()
    while time.time() - t < timeout:
        if proc.poll() is not None:
            fail(f"the {what} stopped while starting. Details: {LOGS / log_name}")
        if up(url):
            return
        time.sleep(0.5)
    fail(f"the {what} did not start within {int(timeout)} seconds. Details: {LOGS / log_name}")


def stop(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is None:
            try:
                if IS_WIN:
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
                else:
                    os.killpg(p.pid, signal.SIGTERM)
            except OSError:
                pass
    for p in procs:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()


def catch_up_scan() -> None:
    """The daily scan only runs while the app is open, so catch up when the data is a day old."""
    try:
        ov = get_json(f"{API}/api/overview")
        if ov["scan"]["running"]:
            return
        last = (ov["scan"].get("last_success") or {}).get("finished_at")
        age_h = 1e9 if not last else (datetime.now(timezone.utc) - datetime.fromisoformat(last).astimezone(timezone.utc)).total_seconds() / 3600
        if age_h > 20:
            req = urllib.request.Request(f"{API}/api/scans", data=b'{"fetch": true}', headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10).close()
            say("Started a scan: " + ("the first one takes about 10 to 15 minutes." if not last else "the data was more than a day old.")
                + " Its progress shows at the top of the window.")
    except Exception as e:  # never block the app from opening
        say(f"(Could not check the last scan: {e})")


# ---- Window ---------------------------------------------------------------------------------------------
def find_browser() -> str | None:
    if IS_WIN:
        roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        rels = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        for rel in rels:
            for root in roots:
                if root and (Path(root) / rel).exists():
                    return str(Path(root) / rel)
        return None
    if sys.platform == "darwin":
        for app in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"):
            if Path(app).exists():
                return app
        return None
    for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def open_window(wait: bool) -> bool:
    """Open the dashboard in its own app window. Returns True if we can tell when it is closed."""
    browser = find_browser()
    if not browser:
        webbrowser.open(UI)
        return False
    profile = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "oalgo2" / "window"
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [browser, f"--app={UI}", f"--user-data-dir={profile}", "--window-size=1500,950", "--no-first-run", "--no-default-browser-check"]
    started = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait:
        return False
    proc.wait()
    # an already-open oalgo2 window takes over the request and this process exits at once
    return time.time() - started > 4


def make_shortcut() -> None:
    """First start only: a Desktop shortcut to Start Here.bat with the oalgo2 icon (Windows)."""
    marker = DATA / ".desktop-shortcut"
    # remake it when the folder moved (for example after copying the data folder into a newer version)
    if not IS_WIN or (marker.exists() and marker.read_text().strip() == str(ROOT)):
        return
    target = ROOT / "Start Here.bat"
    icon = ROOT / "launcher" / "oalgo2.ico"
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'oalgo2 Observatory.lnk'));"
        f"$s.TargetPath='{target}';$s.WorkingDirectory='{ROOT}';$s.IconLocation='{icon}';$s.WindowStyle=7;"
        "$s.Description='oalgo2 stock research observatory';$s.Save()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True)
    if r.returncode == 0:
        DATA.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(ROOT))
        say("Added an 'oalgo2 Observatory' shortcut to your Desktop for next time.")


# ---- Main -----------------------------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Start oalgo2 on this computer.")
    ap.add_argument("--no-window", action="store_true", help="do not open a window (keep running until Ctrl+C)")
    args = ap.parse_args()

    # stop cleanly however we are asked to: Ctrl+C, Ctrl+Break, or a termination request
    def _stop(*_: object) -> None:
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, _stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _stop)
    print("\n  oalgo2 Observatory\n  Research and tracking only. It never places orders.\n", flush=True)

    api_busy, ui_busy = listening(API_PORT), listening(UI_PORT)
    if api_busy and ui_busy and ours():
        say("oalgo2 is already running. Opening its window.")
        if not args.no_window:
            open_window(wait=False)
        return
    if api_busy and not ours():
        fail(f"another program is using port {API_PORT}, which the research engine needs. Close it and try again.")
    if api_busy or ui_busy:
        fail("part of an earlier oalgo2 is still running. Restart your computer, or end the leftover 'python' and 'node' "
             "processes in Task Manager, then try again.")

    node, npx_cli = node_paths()
    build_dashboard(node, npx_cli)

    say("Starting the research engine and the dashboard.")
    env = dict(os.environ, OALGO_DATA_DIR=str(DATA), OALGO_SCHEDULER_ENABLED="true", PYTHONUNBUFFERED="1")
    procs: list[subprocess.Popen] = []
    try:
        api = start([sys.executable, "-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)], BACKEND, env, "research-engine.log")
        procs.append(api)
        ui = start([str(node), str(FRONTEND / "node_modules" / "next" / "dist" / "bin" / "next"), "start", "-H", "127.0.0.1", "-p", str(UI_PORT)],
                   FRONTEND, node_env(node), "dashboard.log")
        procs.append(ui)
        wait_for(f"{API}/api/health", api, "research engine", "research-engine.log")
        wait_for(f"{UI}/login", ui, "dashboard", "dashboard.log")
        catch_up_scan()
        if not args.no_window:
            make_shortcut()
        say(f"Ready: {UI}")
        if not args.no_window and open_window(wait=True):
            say("Window closed. Stopping oalgo2.")
            return
        say("oalgo2 is running. Leave this window open while you use it; close it (or press Ctrl+C) to stop.")
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        fail(f"a part of oalgo2 stopped unexpectedly. Details are in {LOGS}")
    except KeyboardInterrupt:
        say("Stopping oalgo2.")
    finally:
        stop(procs)


if __name__ == "__main__":
    main()
