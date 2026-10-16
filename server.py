"""Local dashboard/API. Bind only to loopback; no authentication or production hosting."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
from pathlib import Path
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

from audit import AuditError, MAX_BYTES, audit_csv

ROOT = Path(__file__).parent
MAX_REQUEST = MAX_BYTES + 250_000
# Lingering close: after replying, read what the client still sends for a bounded time.
LINGER_SECONDS = 1.0
LINGER_BYTES = 64 * 1024
# Fixed allowlist: query values select a preset, never a filesystem path.
DEMOS = {
    "sensor": ("demo.csv", "demo-schema.json", "Synthetic sensor data with eight seeded defects."),
    "repair": ("fixtures/repair-seeded.csv", "profiles/ords-v0.3.json", "Synthetic ORDS v0.3 repair records with twelve seeded findings."),
    "repair-corrected": ("fixtures/repair-corrected.csv", "profiles/ords-v0.3.json", "The same synthetic repair records after corrections."),
}


def store_report(database, report):
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS audits (id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL, report TEXT NOT NULL)")
        cursor = connection.execute("INSERT INTO audits(created_at, report) VALUES (?, ?)", (int(time.time()), json.dumps(report)))
        return cursor.lastrowid


def make_handler(database=None):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, content_type="application/json; charset=utf-8"):
            payload = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def allowed_host(self):
            # Resist browser DNS rebinding; only local literal hosts are accepted.
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def finish(self):
            # Early error replies (403, 404, 413, 415) leave request bytes unread. On Windows,
            # closing a socket with unread incoming bytes sends a reset that can reach the client
            # before the reply. So stop writing, then discard incoming bytes until the client
            # closes, within fixed time and size limits so a slow client cannot hold the thread.
            super().finish()
            try:
                self.connection.shutdown(socket.SHUT_WR)
                self.connection.settimeout(LINGER_SECONDS)
                received = 0
                while received < LINGER_BYTES:
                    chunk = self.connection.recv(4096)
                    if not chunk:
                        break
                    received += len(chunk)
            except OSError:
                pass  # Timeout or connection already closed: nothing left to protect.

        def do_GET(self):
            if not self.allowed_host():
                return self.send(403, {"error": "Local host required."})
            path = urlsplit(self.path).path
            assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path in assets:
                filename, kind = assets[path]
                return self.send(200, (ROOT / filename).read_bytes(), kind)
            if path == "/api/health":
                return self.send(200, {"status": "ok", "version": 1})
            if path == "/api/demo":
                name = parse_qs(urlsplit(self.path).query).get("preset", ["sensor"])[0]
                if name not in DEMOS:
                    return self.send(404, {"error": "Unknown demo preset."})
                csv_file, schema_file, description = DEMOS[name]
                return self.send(200, {"preset": name, "description": description,
                                       "csv": (ROOT / csv_file).read_text(encoding="utf-8"),
                                       "schema": json.loads((ROOT / schema_file).read_text(encoding="utf-8"))})
            if path == "/api/profiles/ords-v0.3":
                return self.send(200, json.loads((ROOT / "profiles/ords-v0.3.json").read_text(encoding="utf-8")))
            return self.send(404, {"error": "Not found."})

        def do_POST(self):
            if not self.allowed_host():
                return self.send(403, {"error": "Local host required."})
            origin = self.headers.get("Origin")
            allowed_origins = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if origin and origin not in allowed_origins:
                return self.send(403, {"error": "Cross-origin requests are not allowed."})
            if urlsplit(self.path).path != "/api/audit":
                return self.send(404, {"error": "Not found."})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.send(415, {"error": "Use application/json."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST:
                    return self.send(413, {"error": "Request must be nonempty and within 5.25 MB."})
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(data, dict) or set(data) - {"csv", "schema"}:
                    raise AuditError("Send an object containing csv and optional schema.")
                report = audit_csv(data.get("csv"), data.get("schema"))
                if database:
                    report["run_id"] = store_report(database, report)
                return self.send(200, report)
            except (AuditError, ValueError, UnicodeError, OverflowError, RecursionError):
                return self.send(400, {"error": "Invalid CSV, JSON or schema. Check types, rules and limits."})
            except sqlite3.Error:
                return self.send(500, {"error": "Could not save report. Check database access."})

        def log_message(self, *args):
            # No payloads or filenames in request logs.
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Run the CSV Triage dashboard locally.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, help="Optional SQLite report history; raw CSV is never stored.")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.db))
    print(f"CSV Triage: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
