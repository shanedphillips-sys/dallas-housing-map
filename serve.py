"""
Local dev server that sends no-cache headers on every response, so the browser
always loads your latest edits. Use this instead of `python -m http.server 8000`:

    python serve.py

(Plain http.server lets the browser cache index.html / app.js, which is why edits
sometimes don't show up without a hard refresh. This server makes that impossible.)
"""
import http.server
import socketserver

PORT = 8000


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), NoCacheHandler) as httpd:
        print(f"No-cache dev server running at http://localhost:{PORT}  (Ctrl+C to stop)")
        httpd.serve_forever()
