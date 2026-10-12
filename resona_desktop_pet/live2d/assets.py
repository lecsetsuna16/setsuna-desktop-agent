"""Serve only the renderer bundle and one selected model on loopback."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import unquote, urlsplit
import secrets


class AssetServer:
    def __init__(self, web_root, model_root):
        roots = {"web": Path(web_root).resolve(), "model": Path(model_root).resolve()}
        prefix = "/" + secrets.token_urlsafe(24)

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def translate_path(self, path):
                parts = unquote(urlsplit(path).path).split("/")
                if len(parts) < 4 or "/" + parts[1] != prefix or parts[2] not in roots:
                    return str(roots["web"] / "__not_found__")
                root = roots[parts[2]]
                candidate = (root / "/".join(parts[3:])).resolve()
                if not candidate.is_relative_to(root) or not candidate.is_file():
                    return str(roots["web"] / "__not_found__")
                return str(candidate)

            def end_headers(self):
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                super().end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(roots["web"])))
        self.thread = Thread(target=self.server.serve_forever, daemon=True, name="Live2D assets")
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}{prefix}/web/index.html"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
