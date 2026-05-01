from __future__ import annotations

import json
import os
import time

from flask import Flask, Response, request, stream_with_context


app = Flask(__name__)


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "skirk-app-engine-probe",
        "mode": os.environ.get("SKIRK_MODE", ""),
        "host": request.host,
    }


@app.get("/stream")
def stream():
    chunks = int(request.args.get("chunks", "5"))
    delay_ms = int(request.args.get("delay_ms", "250"))

    def body():
        for index in range(chunks):
            yield json.dumps({"chunk": index, "ts": time.time()}) + "\n"
            time.sleep(delay_ms / 1000)

    return Response(stream_with_context(body()), mimetype="application/x-ndjson")
