"""E2E용 가짜 Nominatim. /search, /reverse에 고정 응답."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PLACES = [
    {"lat": "37.5796", "lon": "126.9770", "name": "경복궁", "display_name": "경복궁, 사직로, 종로구, 서울, 03045, 대한민국",
     "address": {"city": "서울", "country_code": "kr"}},
    {"lat": "35.6586", "lon": "139.7454", "name": "東京タワー", "display_name": "東京タワー, 芝公園, 港区, 東京都, 日本",
     "address": {"city": "東京都", "country_code": "jp"}},
]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        ua = self.headers.get("User-Agent", "")
        if not ua.startswith("photo-globe"):
            self.send_response(403); self.end_headers(); return
        if u.path == "/search":
            q = qs.get("q", [""])[0]
            body = [p for p in PLACES if q in p["name"] or q in p["display_name"]] or ([] if q != "*" else PLACES)
        elif u.path == "/reverse":
            body = {"lat": qs["lat"][0], "lon": qs["lon"][0], "name": "", "display_name": "세종대로 172, 종로구, 서울, 대한민국",
                    "address": {"road": "세종대로", "city": "서울", "country_code": "kr"}}
        else:
            self.send_response(404); self.end_headers(); return
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
