"""Single-command local dev runner.

Starts FastAPI on :8000 in a background thread, then launches Streamlit
on :8501 pointed at it. Mirrors the production deployment model.

Usage:
    python start.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time


def run_backend() -> None:
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )


def main() -> None:
    os.environ.setdefault("API_BASE_URL", "http://127.0.0.1:8000")
    # The embedded-backend path inside frontend/app.py also starts uvicorn,
    # so disable it here to avoid port contention.
    os.environ["EMBEDDED_BACKEND"] = "0"

    t = threading.Thread(target=run_backend, daemon=True)
    t.start()
    time.sleep(1.5)  # small grace period for uvicorn to bind

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "frontend/app.py",
        "--server.port",
        "8501",
        "--server.headless",
        "true",
    ]
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
