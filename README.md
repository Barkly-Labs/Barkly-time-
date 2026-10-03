# Barkly Work Log + VS Code auto-tracking

This package adds best-effort automatic start/stop timestamps for VS Code workspace sessions to your existing local Barkly Work Log.

## What it does

- Starts a `Barkly Labs` (configurable) session when VS Code opens with a workspace, if the local Python logger is running.
- Attempts to stop and save the session when VS Code shuts down normally.
- Adds a VS Code status-bar item and commands to start/stop tracking manually.
- Keeps the existing SQLite database and all existing log entries. New columns are added safely when the logger starts.
- Tracks **elapsed VS Code window time separately from active work time**. Elapsed time includes idle time and breaks, so it is not automatically counted as active work. Add/edit your actual active work and breaks honestly in your records.
- Adds elapsed time and source to CSV export.

## 1. Back up first

Close the logger if it is running, then copy `barkly_work_log.sqlite3` (if it exists) to a safe backup location. Keep your original script too.

## 2. Start the updated logger

Put `barkly_work_log.py` in your usual logger folder and run:

```powershell
python barkly_work_log.py
```

Open `http://127.0.0.1:8765`. The first run creates a private token at `%USERPROFILE%\.barkly_work_log_token`. Keep it on your computer; do not share it. The logger listens only on `127.0.0.1`.

## 3. Install the VS Code extension locally

This folder is an unpacked extension (no marketplace or internet needed):

1. Open VS Code.
2. Open the Extensions view (`Ctrl+Shift+X`).
3. Click the `...` menu in the Extensions view.
4. Choose **Install from VSIX...** only if you have packaged a VSIX. For this source folder, use the manual development method below.

### Manual development method (recommended for this ZIP)

1. Open the `vscode-extension` folder in a **separate VS Code window**.
2. Press `F5` to launch an Extension Development Host window.
3. Open your actual project folder in that Extension Development Host window.
4. Keep the Python logger running in the background.

The extension auto-starts when a workspace is open. This development-host method is for testing; closing the Extension Development Host should trigger a stop event during normal shutdown.

To package/install it permanently, install Node.js/npm, open a terminal in `vscode-extension`, run `npx @vscode/vsce package`, then install the generated `.vsix` using Extensions `...` → **Install from VSIX...**. Packaging may require downloading the `vsce` package once.

## Settings and commands

Settings (`Ctrl+,`, search `Barkly Work Log`):
- `barklyWorkLog.category`: `Barkly Labs` (default), `Joystick`, or `Other`.
- `barklyWorkLog.autoStart`: start automatically when a workspace is open (default `true`).
- `barklyWorkLog.url`: defaults to `http://127.0.0.1:8765`.

Command Palette (`Ctrl+Shift+P`):
- `Barkly Work Log: Start Tracking`
- `Barkly Work Log: Stop Tracking`
- `Barkly Work Log: Show Status`

## Important limitations

- The Python logger must already be running for start/stop requests to work.
- Shutdown tracking is best effort. A crash, forced termination, power loss, or logger being stopped first can leave a session open. Check the dashboard and close/reconcile any unfinished session; don't treat an open session as a verified end time.
- Use one VS Code window for a given tracked work session. With multiple windows, closing one window may stop the shared session.
- VS Code being open is not proof that you were actively working. The log deliberately separates elapsed window time from active work time.
- This is a neutral personal activity log, not a medical assessment or proof of disability eligibility. Keep records accurate and review them with your representative if useful.

## Data and privacy

Everything is local: SQLite database, token file, and the HTTP server bound to `127.0.0.1`. The extension sends only the selected category and workspace folder name to your local logger.
