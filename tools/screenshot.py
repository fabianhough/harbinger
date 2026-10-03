# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.48"]
# ///
"""Render web/ at the kiosk resolution and write a PNG.

Serves the web/ directory on a local port, opens it in headless Chromium at the
configured viewport, fails if the page overflows that viewport, and saves a screenshot.

Usage:
    uv run tools/screenshot.py [--out preview.png] [--width 2560] [--height 1080]
"""
import argparse
import functools
import http.server
import os
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# A bundled Chromium, if the environment provides one; otherwise Playwright's own.
CHROMIUM = next((p for p in (os.environ.get("CHROMIUM_PATH"), "/opt/pw-browsers/chromium") if p and Path(p).exists()), None)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def serve(directory: Path):
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="preview.png")
    ap.add_argument("--width", type=int, default=2560)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    server, port = serve(WEB)
    try:
        with sync_playwright() as p:
            launch = {"executable_path": CHROMIUM} if CHROMIUM else {}
            browser = p.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": args.width, "height": args.height}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # config.local.js is optional, so its 404 is expected.
            page.on("console", lambda m: errors.append(m.text)
                    if m.type == "error" and "config.local.js" not in (m.location or {}).get("url", "") else None)
            page.goto(f"http://127.0.0.1:{port}/index.html")
            page.wait_for_selector(".pane", timeout=10000)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(300)

            sw, sh = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.scrollHeight]")
            page.screenshot(path=args.out, full_page=False)
            browser.close()
    finally:
        server.shutdown()

    print(f"wrote {args.out} ({args.width}x{args.height}); document {sw}x{sh}")
    ok = True
    if sw > args.width or sh > args.height:
        print(f"FAIL: page overflows viewport ({sw}x{sh} > {args.width}x{args.height})", file=sys.stderr)
        ok = False
    for e in errors:
        print(f"FAIL: console error: {e}", file=sys.stderr)
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
