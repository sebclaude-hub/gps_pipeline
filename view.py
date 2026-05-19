"""Lokaler HTTP-Server für den GPS-Track-Viewer.

Startet einen einfachen HTTP-Server, der die React-App und die Daten
zusammenbringt, und öffnet den Browser automatisch.

Verwendung
----------
    python view.py                    # Sucht output/ im aktuellen Verzeichnis
    python view.py pfad/zu/output/    # Explizites Output-Verzeichnis
    python view.py --port 9000 output/

Routing
-------
    GET /          → gps_viewer/dist/index.html
    GET /assets/*  → gps_viewer/dist/assets/*
    GET /data/*    → output/<dateiname>

Voraussetzung: React-App einmalig gebaut mit:
    cd gps_viewer && npm install && npm run build
"""

import argparse
import http.server
import os
import sys
import threading
import webbrowser
from pathlib import Path

DEFAULT_PORT = 8765
SCRIPT_DIR = Path(__file__).parent.resolve()
VIEWER_DIST = SCRIPT_DIR / "gps_viewer" / "dist"


class GpsViewerHandler(http.server.BaseHTTPRequestHandler):
    """Routet Anfragen auf React-Build und Daten-Verzeichnis."""

    output_dir: Path  # wird vom Server gesetzt, bevor der Handler instanziiert wird

    def log_message(self, fmt, *args):
        # Nur Fehler loggen, nicht jede GET-Anfrage
        if args and str(args[1]) not in ("200", "304"):
            super().log_message(fmt, *args)

    def do_GET(self):
        path = self.path.split("?")[0]  # Query-String ignorieren

        # /data/* → Output-Verzeichnis
        if path.startswith("/data/"):
            rel = path[len("/data/"):]
            file_path = self.output_dir / rel
        # Assets der React-App
        elif path.startswith("/assets/"):
            file_path = VIEWER_DIST / path.lstrip("/")
        # Alles andere → index.html (SPA-Routing)
        else:
            file_path = VIEWER_DIST / "index.html"

        self._serve_file(file_path)

    def _serve_file(self, file_path: Path):
        if not file_path.is_file():
            self.send_error(404, f"Not found: {file_path.name}")
            return

        content_type = _guess_mime(file_path)
        data = file_path.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".js":   "application/javascript",
        ".css":  "text/css",
        ".json": "application/json",
        ".png":  "image/png",
        ".svg":  "image/svg+xml",
        ".ico":  "image/x-icon",
        ".woff2": "font/woff2",
    }.get(ext, "application/octet-stream")


def main():
    parser = argparse.ArgumentParser(
        description="GPS-Track-Viewer starten",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "output_dir", nargs="?", default="output",
        help="Verzeichnis mit den JSON-Daten (Default: output/)",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=DEFAULT_PORT,
        help=f"HTTP-Port (Default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    port = args.port

    # Prüfungen
    if not VIEWER_DIST.is_dir():
        print(
            f"Fehler: React-Build nicht gefunden unter {VIEWER_DIST}\n"
            f"Bitte einmalig bauen:\n"
            f"  cd gps_viewer\n"
            f"  npm install\n"
            f"  npm run build"
        )
        sys.exit(1)

    if not output_dir.is_dir():
        print(f"Fehler: Output-Verzeichnis nicht gefunden: {output_dir}")
        sys.exit(1)

    manifest = output_dir / "manifest.json"
    if not manifest.is_file():
        print(
            f"Warnung: Kein manifest.json in {output_dir}. "
            f"Bitte zuerst 'python -m gps_pipeline --export' ausführen."
        )

    # Handler mit Output-Dir ausstatten
    GpsViewerHandler.output_dir = output_dir

    server = http.server.HTTPServer(("127.0.0.1", port), GpsViewerHandler)
    url = f"http://localhost:{port}"

    print(f"\nGPS-Track-Viewer läuft auf {url}")
    print(f"  React-App: {VIEWER_DIST}")
    print(f"  Daten:     {output_dir}")
    print(f"\nStrg+C zum Beenden.\n")

    # Browser mit kurzer Verzögerung öffnen (Server muss erst bereit sein)
    def open_browser():
        import time
        time.sleep(0.5)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer gestoppt.")


if __name__ == "__main__":
    main()
