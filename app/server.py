"""Web server. Serves the UI and streams each agent step to the browser as server-sent events."""
from __future__ import annotations

import json
import queue
import threading

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

from .budget import budget
from .config import ROOT, settings
from .llm import LLM
from .pipeline import run_check

app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 200_000


def _client() -> str:
    return request.remote_addr or "local"


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    llm = LLM(budget)
    return jsonify({"provider": llm.provider, "model": llm.model, "mock": llm.mock, "mode": settings.mode,
                    "ready": llm.provider != "none", "limits": budget.remaining(_client())})


@app.post("/api/check")
def check():
    payload = request.get_json(silent=True) or {}
    q: queue.Queue = queue.Queue()
    sid = _client()

    def work():
        try:
            run_check(payload, q.put, session_id=sid, mode=payload.get("mode"))
        except Exception as exc:  # last-resort net: the UI must never hang
            q.put({"type": "error", "kind": "internal", "message": f"Unexpected error: {type(exc).__name__}"})
        finally:
            q.put({"type": "done"})

    threading.Thread(target=work, daemon=True).start()

    @stream_with_context
    def stream():
        while True:
            ev = q.get()
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("type") == "done":
                break

    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
