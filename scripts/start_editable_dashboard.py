#!/usr/bin/env python3
"""
AI导演看板 · 通用可编辑分镜看板本地同步服务
用法：
  python3 start_editable_dashboard.py --html <看板.html> --refs-dir <02_分镜参考帧> [--port 8788]
功能：
  1. 网页端上传/拖入参考图 → 自动存入 02_分镜参考帧/XX_简写/
  2. 网页端点击 × 删除参考图 → 自动移入该镜 XX_简写/_弃用/（防误传、可找回）
  3. 网页端 Cmd+S 保存 → 同步写回 HTML 与 storyboard_manifest.json
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

HTML_PATH: Path = Path()
REFS_DIR: Path = Path()
MANIFEST_PATH: Path = Path()


def sanitize_filename(name: str) -> str:
    name = os.path.basename(name or "ref.png")
    name = re.sub(r"[^\w\-.()\u4e00-\u9fff]+", "_", name)
    return name or "ref.png"


def shot_folder(shot_label: str) -> str:
    m = re.search(r"(\d+)", shot_label or "")
    num = int(m.group(1)) if m else 0
    prefix = f"{num:02d}"
    if REFS_DIR.exists():
        for p in sorted(REFS_DIR.iterdir()):
            if p.is_dir() and (p.name == prefix or p.name.startswith(prefix + "_")):
                return p.name
    return prefix


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[AI导演看板] {self.address_string()} - {format % args}")

    def _send_json(self, code: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html", "/editable"):
            if not HTML_PATH.exists():
                self.send_error(404, "Editable HTML not found")
                return
            data = HTML_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/health":
            self._send_json(200, {
                "ok": True,
                "refs_dir": str(REFS_DIR),
                "html_path": str(HTML_PATH),
                "manifest_path": str(MANIFEST_PATH),
            })
            return

        if parsed.path.startswith("/refs/"):
            rel = unquote(parsed.path[len("/refs/"):]).lstrip("/")
            target = (REFS_DIR / rel).resolve()
            if not str(target).startswith(str(REFS_DIR.resolve())) or not target.is_file():
                self.send_error(404, "Ref file not found")
                return
            ctype, _ = mimetypes.guess_type(str(target))
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"ok": False, "error": f"Invalid JSON: {e}"})
            return

        if parsed.path == "/api/upload_ref":
            shot_id = body.get("shotId", "Shot 00")
            filename = sanitize_filename(body.get("filename", "ref.png"))
            data_url = body.get("dataUrl", "")
            if "," not in data_url:
                self._send_json(400, {"ok": False, "error": "Missing dataUrl payload"})
                return
            _, b64 = data_url.split(",", 1)
            img_bytes = base64.b64decode(b64)

            folder = shot_folder(shot_id)
            shot_dir = REFS_DIR / folder
            shot_dir.mkdir(parents=True, exist_ok=True)

            target_path = shot_dir / filename
            stem, ext = os.path.splitext(filename)
            idx = 1
            while target_path.exists():
                target_path = shot_dir / f"{stem}_{idx}{ext}"
                idx += 1

            target_path.write_bytes(img_bytes)
            self._send_json(200, {
                "ok": True,
                "shotId": shot_id,
                "folder": folder,
                "savedPath": str(target_path),
                "filename": target_path.name,
                "url": f"/refs/{quote(folder)}/{quote(target_path.name)}",
            })
            return

        if parsed.path == "/api/archive_ref":
            img_src = body.get("imgSrc", "")
            shot_id = body.get("shotId", "Shot 00")
            if not img_src.startswith("/refs/"):
                self._send_json(200, {"ok": True, "moved": False})
                return
            rel = unquote(img_src[len("/refs/"):]).lstrip("/")
            src_path = (REFS_DIR / rel).resolve()
            if not str(src_path).startswith(str(REFS_DIR.resolve())) or not src_path.is_file():
                self._send_json(200, {"ok": True, "moved": False})
                return

            trash_dir = src_path.parent / "_弃用"
            trash_dir.mkdir(exist_ok=True)
            dst_path = trash_dir / src_path.name
            stem, ext = os.path.splitext(src_path.name)
            idx = 1
            while dst_path.exists():
                dst_path = trash_dir / f"{stem}_{idx}{ext}"
                idx += 1
            shutil.move(str(src_path), str(dst_path))
            self._send_json(200, {
                "ok": True,
                "moved": True,
                "shotId": shot_id,
                "archivedPath": str(dst_path),
            })
            return

        if parsed.path == "/api/save_dashboard":
            html_content = body.get("html")
            manifest = body.get("manifest")
            if html_content:
                HTML_PATH.write_text(html_content, encoding="utf-8")
            if manifest is not None:
                MANIFEST_PATH.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            self._send_json(200, {
                "ok": True,
                "htmlSaved": bool(html_content),
                "manifestSaved": manifest is not None,
                "manifestPath": str(MANIFEST_PATH),
            })
            return

        self._send_json(404, {"ok": False, "error": "Unknown endpoint"})


def main():
    global HTML_PATH, REFS_DIR, MANIFEST_PATH
    parser = argparse.ArgumentParser(description="AI导演看板本地同步服务")
    parser.add_argument("--html", required=True, help="可编辑分镜看板 HTML 路径")
    parser.add_argument("--refs-dir", required=True, help="02_分镜参考帧 目录路径")
    parser.add_argument("--port", type=int, default=8788, help="本地服务端口（默认 8788）")
    args = parser.parse_args()

    HTML_PATH = Path(args.html).resolve()
    REFS_DIR = Path(args.refs_dir).resolve()
    MANIFEST_PATH = HTML_PATH.parent / "storyboard_manifest.json"

    server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"AI导演看板服务已启动: {url}")
    print(f"参考图目录: {REFS_DIR}")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n看板服务已停止。")


if __name__ == "__main__":
    main()
