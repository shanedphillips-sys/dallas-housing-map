"""
Local dev server for the webmap: no-cache headers (so edits always show) AND HTTP
Range support (so the PMTiles layers — parcels, buildings — load). Use this instead
of `python -m http.server`:

    python serve.py            # http://localhost:8000
    python serve.py 8001       # custom port

Why Range matters: pmtiles.js reads each vector tile by requesting a byte range.
Plain http.server (and the old version of this script) ignore the Range header and
return the whole ~90 MB file with a 200, so pmtiles.js can't parse tiles and the
parcels / buildings layers render blank at every zoom. This server answers 206
Partial Content. GitHub Pages supports Range natively, so this is only for local
preview.
"""
import io
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class DevHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # never cache during local dev, so edits always show without a hard refresh
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()
        path = self.translate_path(self.path)
        m = re.match(r"bytes=(\d+)-(\d*)$", rng.strip())
        if not m or not os.path.isfile(path):
            return super().send_head()  # not a simple single range -> fall back to 200
        size = os.path.getsize(path)
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        with open(path, "rb") as fh:
            fh.seek(start)
            data = fh.read(end - start + 1)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        return io.BytesIO(data)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    httpd = ThreadingHTTPServer(("", port), DevHandler)
    print(f"Dev server (no-cache + Range) at http://localhost:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
