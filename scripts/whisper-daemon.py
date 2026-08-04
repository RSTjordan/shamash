"""Warm transcription daemon — keeps the Whisper model loaded in RAM.

Only used when features.voice_notes is true. Serves the command watcher on
localhost so voice notes transcribe in seconds instead of paying the ~15-20s
model load on every note. Started (and restarted if it dies) by the command
watcher; binds the port before loading the model so a second copy exits
immediately instead of loading a duplicate model.

  GET  /health              -> {"ok": true, "loaded": bool, "model": str|null}
  POST /transcribe {"path"} -> {"ok": true, "text": str} | {"ok": false, "error": str}

Only files inside the active bridge stores are accepted (voice notes land in
<bridge>/store/<chat_jid>/).
"""

import json
import logging
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path

from faster_whisper import WhisperModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

CFG = config.load()
# Voice notes land under the bridge stores — scope reads to them (NOT the
# whole project: that tree also holds the bridge auth tokens).
MEDIA_ROOTS = tuple(
    Path(channel["store"]) for channel in CFG["active_channels"].values()
)
HOST, PORT = "127.0.0.1", 8090
MODELS_DIR = str(Path(CFG["root"]) / "whisper-env" / "models")
_PRIMARY = CFG["features"].get("voice_model") or "ivrit-ai/whisper-large-v3-turbo-ct2"
CANDIDATES = tuple(dict.fromkeys((_PRIMARY, "large-v3-turbo")))

LOG_DIR = Path(CFG["paths"]["logs"])
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    handlers=[
        RotatingFileHandler(
            str(LOG_DIR / "whisper-daemon.log"),
            maxBytes=2_000_000,
            backupCount=2,
            encoding="utf-8",
        )
    ],
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

_model: WhisperModel | None = None
_model_id: str | None = None
_transcribe_lock = threading.Lock()
_loader_lock = threading.Lock()
_loading = False


def load_model() -> bool:
    global _model, _model_id
    # local_files_only first: once cached, loading must not depend on
    # HuggingFace being reachable. Network retry only for a cold cache.
    for model_id in CANDIDATES:
        for local_only in (True, False):
            try:
                t0 = time.time()
                model = WhisperModel(
                    model_id,
                    device="cpu",
                    compute_type="int8",
                    download_root=MODELS_DIR,
                    cpu_threads=12,
                    local_files_only=local_only,
                )
                _model, _model_id = model, model_id
                logging.info(
                    "model %s loaded in %.1fs (local_only=%s)",
                    model_id, time.time() - t0, local_only,
                )
                return True
            except Exception:
                logging.exception(
                    "loading %s failed (local_only=%s)", model_id, local_only
                )
    return False


def start_loader() -> None:
    """Kick off (or retry) the model load without ever running two loads."""
    global _loading
    with _loader_lock:
        if _loading or _model is not None:
            return
        _loading = True

    def _run():
        global _loading
        try:
            load_model()
        finally:
            _loading = False

    threading.Thread(target=_run, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # default logs to stderr; keep it in our log
        logging.info("http %s", fmt % args)

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "loaded": _model is not None, "model": _model_id})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/transcribe":
            return self._json(404, {"ok": False, "error": "not found"})
        if _model is None:
            start_loader()  # self-heal: a failed load retries on next request
            return self._json(503, {"ok": False, "error": "model still loading"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            path = Path(str(body["path"])).resolve()
        except Exception as e:
            return self._json(400, {"ok": False, "error": f"bad request: {e}"})
        if not any(path.is_relative_to(root) for root in MEDIA_ROOTS):
            return self._json(403, {"ok": False, "error": "path outside media stores"})
        if not path.is_file():
            return self._json(404, {"ok": False, "error": f"no such file: {path}"})
        try:
            with _transcribe_lock:
                t0 = time.time()
                segments, _info = _model.transcribe(str(path), vad_filter=True)
                text = " ".join(s.text.strip() for s in segments).strip()
            logging.info(
                "transcribed %s in %.1fs: %.80s", path.name, time.time() - t0, text
            )
            self._json(200, {"ok": True, "text": text})
        except Exception as e:
            logging.exception("transcribe failed for %s", path)
            self._json(500, {"ok": False, "error": str(e)})


def main() -> int:
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as e:
        logging.error("bind %s:%s failed (already running?): %s", HOST, PORT, e)
        return 1
    logging.info("listening on %s:%s, loading model...", HOST, PORT)
    start_loader()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
