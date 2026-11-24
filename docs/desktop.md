# Running oalgo2 on your Windows computer

One file starts everything: **Start Here.bat**. Nothing needs to be installed by hand.

## First time

1. Open the repository on GitHub: `github.com/vyomruppar/oalgo2`.
2. Choose **Code** → **Download ZIP**.
3. In your Downloads folder, right-click the ZIP and choose **Extract All**, then **Extract**. Put the folder wherever you like, for example in Documents. Running it from inside the ZIP does not work, and the file tells you so if you try.
4. In the extracted folder, double-click **Start Here** (`Start Here.bat`).
5. Windows may warn you, because the file was downloaded:
   - "Windows protected your PC": click **More info**, then **Run anyway**.
   - "Open File - Security Warning": click **Run**.
6. A black window shows progress. The first start downloads about 2 GB (Python, the AI model, the dashboard's parts) and takes about 10 minutes on a typical connection.
7. The dashboard opens in its own window. If you have never scanned, the first scan starts by itself and takes 10 to 15 minutes; its progress shows at the top of the window.
8. Add the stocks you own under **My portfolio**.

The first start also puts an **oalgo2 Observatory** shortcut on your Desktop.

## Every day

- Double-click the Desktop shortcut (or `Start Here.bat`). It opens in a few seconds.
- **Close the oalgo2 window to stop it.** The black window closes with it.
- If oalgo2 is already open, starting it again just brings the window back.
- The automatic scan runs on weekdays at 22:30 UTC while oalgo2 is open. If it was closed then, a catch-up scan starts the next time you open it, whenever the data is more than a day old.

## Good to know

| Topic | Detail |
|---|---|
| Where your data lives | The `data` folder inside the oalgo2 folder: your holdings, settings, prices and scan history. |
| Privacy | Everything runs on your computer and is reachable only from it (127.0.0.1). There is no password because nothing is exposed to your network. |
| Internet | Needed for scans, prices, filings and headlines. Without it the dashboard still opens with the last data. |
| The window | It uses Microsoft Edge (or Chrome) in app mode, with its own separate profile, so it does not touch your normal browsing. Without either, it opens in your default browser and you stop oalgo2 by closing the black window. |
| Disk space | About 2.5 GB after the first start, plus the data folder (a few hundred MB). |

## Updating to a newer version

Click **Update** in the status bar at the top of the app (it appears when a newer version exists; **Scans and data** has a "Software updates" card with a "Check for updates" button). Then click **Update now**. oalgo2 downloads the new version, closes, installs it, rebuilds the dashboard if needed and reopens by itself. Your data folder, holdings and installed packages are never touched. Updates are blocked while a scan is running.

If the new version fails to start, the old version is restored automatically and that broken version is not offered again until a newer one is published.

Updates come from the `claude/admiring-hypatia-8mav3t` branch of `vyomruppar/oalgo2` on GitHub (set in `launcher/update.json`). The check needs internet and is cached for 30 minutes.

**One-time step if your copy has no Update button:** it was installed before updating existed. Do the manual update once: close oalgo2, download and extract the new ZIP, copy your `data` folder into it, start it, delete the old folder. After that the button does everything.

## If something goes wrong

The black window says what failed and stays open. Detailed logs are in `data\logs`:

| Message | What to do |
|---|---|
| "another program is using port 8765" | Something else uses that port. Close it, or restart your computer. |
| "part of an earlier oalgo2 is still running" | Restart your computer, or end leftover `python` and `node` processes in Task Manager. |
| "setting up the dashboard failed" | Usually a dropped connection during the first download. Start again; it picks up where it stopped. The details are in `data\logs\dashboard-build.log`. |
| The window shows "Cannot reach the research backend" | The research engine stopped. Close the window and start again; see `data\logs\research-engine.log`. |

## Removing it

Close oalgo2 and delete its folder and the Desktop shortcut. To also remove the shared tools it downloaded: the uv tool lives in `%USERPROFILE%\.local\bin`, its Python and package cache in `%LOCALAPPDATA%\uv`, and the window's profile in `%LOCALAPPDATA%\oalgo2`.
