
#!/usr/bin/env python3
"""
Barkly Work Log
===============

One-file, dependency-free local work/capacity logger.

Run:
    python barkly_work_log.py

Then open:
    http://127.0.0.1:8765

Creates:
    barkly_work_log.sqlite3

The database stays local on your computer.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from datetime import datetime
from pathlib import Path
from html import escape
import csv
import io
import json
import re
import secrets
import sqlite3
import webbrowser

HOST = "127.0.0.1"
PORT = 8765

DB = Path(__file__).with_name("barkly_work_log.sqlite3")
TOKEN_FILE = Path.home() / ".barkly_work_log_token"

CATEGORIES = [
    "Barkly Labs",
    "Joystick",
    "Other",
]

ENERGY = [
    "Fine",
    "Tired",
    "Burned out",
    "Completely wiped out",
]

AFTER_EFFECTS = [
    "Nothing unusual",
    "Needed significant rest",
    "Could not do another task",
    "Needed to lie down/sleep",
    "Needed help with something",
]


# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            started_at TEXT NOT NULL,
            stopped_at TEXT NOT NULL,
            active_seconds INTEGER NOT NULL DEFAULT 0,
            break_seconds INTEGER NOT NULL DEFAULT 0,
            breaks INTEGER NOT NULL DEFAULT 0,
            energy TEXT NOT NULL,
            after_effect TEXT NOT NULL,
            income REAL NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            elapsed_seconds INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'manual',
            is_open INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Safe, additive migrations preserve existing logs.
    columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(sessions)")
    }

    migrations = {
        "elapsed_seconds":
            "ALTER TABLE sessions ADD COLUMN elapsed_seconds "
            "INTEGER NOT NULL DEFAULT 0",
        "source":
            "ALTER TABLE sessions ADD COLUMN source "
            "TEXT NOT NULL DEFAULT 'manual'",
        "is_open":
            "ALTER TABLE sessions ADD COLUMN is_open "
            "INTEGER NOT NULL DEFAULT 0",
    }

    for column, statement in migrations.items():
        if column not in columns:
            db.execute(statement)

    db.commit()
    return db


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def format_seconds(seconds):
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def parse_duration(value):
    """
    Accepts:
        90
        90m
        1h 30m
        1 hour 30 minutes
        45s

    A plain number is interpreted as minutes.
    """
    value = str(value or "").strip().lower()

    if not value:
        return 0

    matches = re.findall(
        r"(\d+(?:\.\d+)?)\s*"
        r"(h|hr|hrs|hour|hours|"
        r"m|min|mins|minute|minutes|"
        r"s|sec|secs|second|seconds)",
        value,
    )

    total = 0

    for number, unit in matches:
        number = float(number)

        if unit.startswith("h"):
            total += int(number * 3600)
        elif unit.startswith("m"):
            total += int(number * 60)
        else:
            total += int(number)

    # Plain number = minutes.
    if not matches and re.fullmatch(r"\d+(?:\.\d+)?", value):
        total = int(float(value) * 60)

    return max(0, total)


def safe_nonnegative_int(value, default=0):
    """Convert a value to a nonnegative integer safely."""
    try:
        number = int(value)
        return max(0, number)
    except (TypeError, ValueError, OverflowError):
        return default


def today():
    return datetime.now().date().isoformat()


def safe_text(value, limit=4000):
    """Convert untrusted input into bounded plain text."""
    if value is None:
        return ""
    return str(value).strip()[:limit]


def html_text(value):
    """Escape dynamic values before placing them into HTML."""
    return escape(str(value if value is not None else ""), quote=True)


def selected_options(values, selected):
    result = ""

    for value in values:
        safe = html_text(value)
        is_selected = " selected" if value == selected else ""
        result += f'<option value="{safe}"{is_selected}>{safe}</option>'

    return result


# ------------------------------------------------------------
# HTML
# ------------------------------------------------------------

def page(body, title="Barkly Work Log"):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_text(title)}</title>
<style>
:root {{
    color-scheme: light dark;
    --bg: #f5f2f8;
    --card: #ffffff;
    --text: #241f29;
    --muted: #6e6575;
    --border: #ddd5e3;
    --accent: #7b4bb3;
    --accent-light: #efe5fa;
}}
@media (prefers-color-scheme: dark) {{
    :root {{
        --bg: #17141a;
        --card: #211d25;
        --text: #f5eef9;
        --muted: #b9adbf;
        --border: #3a3240;
        --accent: #b78be8;
        --accent-light: #332642;
    }}
}}
* {{
    box-sizing: border-box;
}}
body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
}}
main {{
    max-width: 1050px;
    margin: auto;
    padding: 28px 18px 60px;
}}
h1 {{
    margin-bottom: 5px;
}}
h2 {{
    margin-top: 0;
}}
.sub {{
    color: var(--muted);
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
}}
.card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 20px;
    box-shadow: 0 4px 18px rgba(0,0,0,.05);
}}
label {{
    display: block;
    font-weight: 650;
    margin: 13px 0 6px;
}}
input, select, textarea {{
    width: 100%;
    padding: 11px 12px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--card);
    color: var(--text);
    font: inherit;
}}
textarea {{
    min-height: 100px;
    resize: vertical;
}}
button, .button {{
    display: inline-block;
    border: 0;
    border-radius: 11px;
    padding: 11px 15px;
    background: var(--accent);
    color: white;
    font-weight: 700;
    cursor: pointer;
    text-decoration: none;
    margin-top: 14px;
}}
.secondary {{
    background: var(--accent-light);
    color: var(--text);
}}
.notice {{
    padding: 14px;
    border-radius: 13px;
    background: var(--accent-light);
    margin-bottom: 16px;
}}
.stat {{
    font-size: 1.7rem;
    font-weight: 800;
}}
.muted {{
    color: var(--muted);
}}
.small {{
    font-size: .88rem;
}}
.actions {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 16px;
}}
.badge {{
    display: inline-block;
    padding: 4px 8px;
    border-radius: 999px;
    background: var(--accent-light);
}}
.table-wrap {{
    overflow-x: auto;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: .9rem;
}}
th, td {{
    text-align: left;
    padding: 9px 6px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
}}
</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""


# ------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------

def dashboard():
    db = connect()

    rows = db.execute("""
        SELECT *
        FROM sessions
        ORDER BY id DESC
    """).fetchall()

    db.close()

    today_rows = [
        row for row in rows
        if row["started_at"][:10] == today()
    ]

    today_active = sum(row["active_seconds"] for row in today_rows)
    today_elapsed = sum(row["elapsed_seconds"] for row in today_rows)
    today_breaks = sum(row["break_seconds"] for row in today_rows)
    today_income = sum(row["income"] for row in today_rows)
    today_break_count = sum(row["breaks"] for row in today_rows)

    recent = rows[:15]
    history = ""

    for row in recent:
        history += f"""
        <tr>
            <td>{html_text(row["started_at"].replace("T", " "))}</td>
            <td><span class="badge">{html_text(row["category"])}</span></td>
            <td>{format_seconds(row["active_seconds"])}</td>
            <td>{format_seconds(row["elapsed_seconds"])}</td>
            <td>{row["breaks"]}</td>
            <td>{html_text(row["energy"])}</td>
            <td>{html_text(row["after_effect"])}</td>
            <td>${row["income"]:.2f}</td>
            <td class="small">{html_text(row["notes"][:120])}</td>
        </tr>
        """

    if not history:
        history = """
        <tr>
            <td colspan="9" class="muted">
                No sessions yet. Your first one can be tiny.
            </td>
        </tr>
        """

    category_options = selected_options(CATEGORIES, CATEGORIES[0])
    energy_options = selected_options(ENERGY, ENERGY[0])
    after_options = selected_options(AFTER_EFFECTS, AFTER_EFFECTS[0])

    body = f"""
<h1>🐶 Barkly Work Log</h1>
<p class="sub">
    A tiny local logger for work, breaks, capacity, fatigue,
    and what happens afterward.
</p>

<div class="notice">
<strong>Today:</strong>
{format_seconds(today_active)} active work
· {format_seconds(today_breaks)} break time
· {format_seconds(today_elapsed)} VS Code session time
· ${today_income:.2f} received
</div>

<div class="actions">
    <a class="button secondary" href="/export">Export CSV</a>
    <a class="button secondary" href="/">Refresh</a>
</div>

<div class="grid">
<div class="card">
<h2>🐾 Log a session</h2>
<p class="sub">Just record what actually happened.</p>

<form method="post" action="/add">
<label>What were you doing?</label>
<select name="category">{category_options}</select>

<div class="grid">
<div>
<label>Started</label>
<input type="datetime-local" name="started_at" required>
</div>
<div>
<label>Stopped</label>
<input type="datetime-local" name="stopped_at" required>
</div>
</div>

<label>Active work time</label>
<input type="text" name="active_time"
       placeholder="Example: 1h 30m" required>

<label>Break time</label>
<input type="text" name="break_time"
       placeholder="Example: 20m">

<label>Number of breaks</label>
<input type="number" name="breaks" min="0" value="0">

<label>How did you feel afterward?</label>
<select name="energy">{energy_options}</select>

<label>What happened afterward?</label>
<select name="after_effect">{after_options}</select>

<label>Income actually received</label>
<input type="number" name="income" min="0" step="0.01" value="0.00">

<label>Notes</label>
<textarea name="notes"
    placeholder="What you accomplished, what you couldn't finish, help you needed, fatigue, etc."></textarea>

<button type="submit">Save session</button>
</form>
</div>

<div class="card">
<h2>📊 Today</h2>

<div class="stat">{format_seconds(today_active)}</div>
<div class="muted">active work</div>

<br>

<div class="stat">{today_break_count}</div>
<div class="muted">breaks</div>

<br>

<div class="stat">{format_seconds(today_breaks)}</div>
<div class="muted">break time</div>

<br>

<div class="stat">${today_income:.2f}</div>
<div class="muted">income actually received</div>

<br>

<p class="small muted">
This is a neutral activity log.
A good day belongs in the log too.
A difficult day belongs in the log too.
The goal is an honest record, not a score.
</p>
</div>
</div>

<div class="card" style="margin-top:16px">
<h2>Recent sessions</h2>
<div class="table-wrap">
<table>
<thead>
<tr>
<th>Started</th>
<th>Type</th>
<th>Active</th>
<th>VS Code elapsed</th>
<th>Breaks</th>
<th>After</th>
<th>Effect</th>
<th>Income</th>
<th>Notes</th>
</tr>
</thead>
<tbody>
{history}
</tbody>
</table>
</div>
</div>
"""

    return page(body)


# ------------------------------------------------------------
# HTTP SERVER
# ------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    def send_html(self, content, status=200):
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "vscode-webview://*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "vscode-webview://*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Barkly-Token",
        )
        self.end_headers()

    def do_GET(self):
        request_path = urlparse(self.path).path

        if request_path == "/":
            self.send_html(dashboard())
            return

        if request_path == "/export":
            db = connect()
            rows = db.execute("""
                SELECT *
                FROM sessions
                ORDER BY started_at
            """).fetchall()
            db.close()

            output = io.StringIO()
            writer = csv.writer(output)

            writer.writerow([
                "id",
                "category",
                "started_at",
                "stopped_at",
                "active_seconds",
                "elapsed_seconds",
                "source",
                "break_seconds",
                "breaks",
                "energy_after",
                "after_effect",
                "income_received",
                "notes",
            ])

            for row in rows:
                writer.writerow([
                    row["id"],
                    row["category"],
                    row["started_at"],
                    row["stopped_at"],
                    row["active_seconds"],
                    row["elapsed_seconds"],
                    row["source"],
                    row["break_seconds"],
                    row["breaks"],
                    row["energy"],
                    row["after_effect"],
                    row["income"],
                    row["notes"],
                ])

            data = output.getvalue().encode("utf-8-sig")

            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header(
                "Content-Disposition",
                'attachment; filename="barkly_work_log.csv"',
            )
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_html(
            page("""
                <h1>Not found</h1>
                <a class="button" href="/">Go home</a>
            """),
            404,
        )

    def do_POST(self):
        request_path = urlparse(self.path).path

        # ----------------------------------------------------
        # AUTHENTICATED VS CODE API
        # ----------------------------------------------------

        if request_path in (
            "/vscode/start",
            "/vscode/stop",
            "/vscode/status",
        ):
            supplied = self.headers.get("X-Barkly-Token", "")

            try:
                expected = TOKEN_FILE.read_text(encoding="utf-8").strip()
            except OSError:
                expected = ""

            if not expected or not secrets.compare_digest(supplied, expected):
                self.send_json({
                    "ok": False,
                    "error": "Unauthorized. Start the logger and check the token file.",
                }, 401)
                return

            length = safe_nonnegative_int(
                self.headers.get("Content-Length", "0")
            )

            if length > 100_000:
                self.send_json({
                    "ok": False,
                    "error": "Request body is too large.",
                }, 413)
                return

            raw = self.rfile.read(length).decode("utf-8") if length else "{}"

            try:
                payload = json.loads(raw or "{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json({
                    "ok": False,
                    "error": "Invalid JSON.",
                }, 400)
                return

            if not isinstance(payload, dict):
                self.send_json({
                    "ok": False,
                    "error": "JSON body must be an object.",
                }, 400)
                return

            db = connect()

            # STATUS
            if request_path == "/vscode/status":
                row = db.execute("""
                    SELECT id, category, started_at
                    FROM sessions
                    WHERE is_open=1
                    ORDER BY id DESC
                    LIMIT 1
                """).fetchone()

                db.close()

                self.send_json({
                    "ok": True,
                    "tracking": bool(row),
                    "session": dict(row) if row else None,
                })
                return

            # START
            if request_path == "/vscode/start":
                existing = db.execute("""
                    SELECT id, category, started_at
                    FROM sessions
                    WHERE is_open=1
                    ORDER BY id DESC
                    LIMIT 1
                """).fetchone()

                if existing:
                    db.close()
                    self.send_json({
                        "ok": True,
                        "already_tracking": True,
                        "session": dict(existing),
                    })
                    return

                category = payload.get("category", "Barkly Labs")

                if category not in CATEGORIES:
                    category = "Barkly Labs"

                started = datetime.now().isoformat(
                    sep=" ",
                    timespec="seconds",
                )

                workspace = safe_text(
                    payload.get("workspace", "VS Code workspace"),
                    300,
                )

                notes = (
                    "Automatically tracked VS Code window duration. "
                    "Elapsed time includes idle time and breaks; "
                    "review separately from active work. "
                    f"Workspace: {workspace}"
                )

                cursor = db.execute("""
                    INSERT INTO sessions (
                        category,
                        started_at,
                        stopped_at,
                        active_seconds,
                        break_seconds,
                        breaks,
                        energy,
                        after_effect,
                        income,
                        notes,
                        elapsed_seconds,
                        source,
                        is_open
                    )
                    VALUES (?, ?, ?, 0, 0, 0, ?, ?, 0, ?, 0, 'vscode', 1)
                """, (
                    category,
                    started,
                    started,
                    ENERGY[0],
                    AFTER_EFFECTS[0],
                    notes,
                ))

                db.commit()

                row = db.execute("""
                    SELECT id, category, started_at
                    FROM sessions
                    WHERE id=?
                """, (cursor.lastrowid,)).fetchone()

                db.close()

                self.send_json({
                    "ok": True,
                    "started": True,
                    "session": dict(row),
                })
                return

            # STOP
            # Only stop the current VS Code session.
            # Manual entries are never modified here.
            row = db.execute("""
                SELECT id, started_at, notes
                FROM sessions
                WHERE is_open=1 AND source='vscode'
                ORDER BY id DESC
                LIMIT 1
            """).fetchone()

            if not row:
                db.close()
                self.send_json({
                    "ok": True,
                    "stopped": False,
                    "message": "No VS Code session was open.",
                })
                return

            stopped = datetime.now().isoformat(
                sep=" ",
                timespec="seconds",
            )

            try:
                start_dt = datetime.fromisoformat(row["started_at"])
                elapsed = max(
                    0,
                    int(
                        (
                            datetime.fromisoformat(stopped) - start_dt
                        ).total_seconds()
                    ),
                )
            except (ValueError, TypeError):
                elapsed = 0

            energy = payload.get("energy", ENERGY[0])
            if energy not in ENERGY:
                energy = ENERGY[0]

            after_effect = payload.get(
                "after_effect",
                AFTER_EFFECTS[0],
            )
            if after_effect not in AFTER_EFFECTS:
                after_effect = AFTER_EFFECTS[0]

            # These values come from the VS Code check-in.
            # They are separate from automatically measured elapsed time.
            active_seconds = safe_nonnegative_int(
                payload.get("active_seconds", 0)
            )
            break_seconds = safe_nonnegative_int(
                payload.get("break_seconds", 0)
            )
            breaks = safe_nonnegative_int(payload.get("breaks", 0))

            # Keep notes bounded and append the check-in to the
            # automatically generated workspace/session notes.
            user_notes = safe_text(payload.get("notes", ""), 4000)
            notes = row["notes"] or ""

            if user_notes:
                notes += "\n\nSession effects:\n" + user_notes

            db.execute("""
                UPDATE sessions
                SET stopped_at=?,
                    elapsed_seconds=?,
                    active_seconds=?,
                    break_seconds=?,
                    breaks=?,
                    is_open=0,
                    energy=?,
                    after_effect=?,
                    notes=?
                WHERE id=?
            """, (
                stopped,
                elapsed,
                active_seconds,
                break_seconds,
                breaks,
                energy,
                after_effect,
                notes,
                row["id"],
            ))

            db.commit()
            db.close()

            self.send_json({
                "ok": True,
                "stopped": True,
                "elapsed_seconds": elapsed,
                "active_seconds": active_seconds,
                "break_seconds": break_seconds,
                "breaks": breaks,
            })
            return

        # ----------------------------------------------------
        # MANUAL WEB FORM
        # ----------------------------------------------------

        if request_path != "/add":
            self.send_html(
                page("<h1>Not found</h1>"),
                404,
            )
            return

        length = safe_nonnegative_int(
            self.headers.get("Content-Length", "0")
        )

        if length > 100_000:
            self.send_html(
                page("<h1>Form submission is too large.</h1>"),
                413,
            )
            return

        raw = self.rfile.read(length).decode("utf-8")
        form = parse_qs(raw)

        def get(name, default=""):
            return form.get(name, [default])[0].strip()

        started = get("started_at").replace("T", " ")
        stopped = get("stopped_at").replace("T", " ")

        try:
            started_dt = datetime.fromisoformat(started)
            stopped_dt = datetime.fromisoformat(stopped)
        except ValueError:
            self.send_html(
                page("""
                    <h1>Invalid date/time</h1>
                    <a class="button" href="/">Go back</a>
                """),
                400,
            )
            return

        if stopped_dt < started_dt:
            self.send_html(
                page("""
                    <h1>Stopped time is before started time.</h1>
                    <a class="button" href="/">Go back</a>
                """),
                400,
            )
            return

        category = get("category") or "Other"
        if category not in CATEGORIES:
            category = "Other"

        active_seconds = parse_duration(get("active_time"))
        break_seconds = parse_duration(get("break_time"))
        breaks = safe_nonnegative_int(get("breaks", "0"))

        try:
            income = max(0.0, float(get("income", "0") or 0))
        except (ValueError, OverflowError):
            income = 0.0

        energy = get("energy") or ENERGY[0]
        if energy not in ENERGY:
            energy = ENERGY[0]

        after_effect = get("after_effect") or AFTER_EFFECTS[0]
        if after_effect not in AFTER_EFFECTS:
            after_effect = AFTER_EFFECTS[0]

        notes = safe_text(get("notes"), 4000)

        db = connect()
        db.execute("""
            INSERT INTO sessions (
                category,
                started_at,
                stopped_at,
                active_seconds,
                break_seconds,
                breaks,
                energy,
                after_effect,
                income,
                notes,
                elapsed_seconds,
                source,
                is_open
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', 0)
        """, (
            category,
            started,
            stopped,
            active_seconds,
            break_seconds,
            breaks,
            energy,
            after_effect,
            income,
            notes,
            max(
                0,
                int((stopped_dt - started_dt).total_seconds()),
            ),
        ))

        db.commit()
        db.close()

        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():
    connect().close()

    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(
            secrets.token_urlsafe(32),
            encoding="utf-8",
        )

        try:
            TOKEN_FILE.chmod(0o600)
        except OSError:
            pass

    server = ThreadingHTTPServer(
        (HOST, PORT),
        Handler,
    )

    url = f"http://{HOST}:{PORT}"

    print()
    print("🐶 Barkly Work Log")
    print()
    print(f"Open: {url}")
    print()
    print(f"Database: {DB}")
    print(f"VS Code token: {TOKEN_FILE}")
    print()
    print("Press Ctrl+C to stop.")
    print()

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("Barkly Work Log stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()