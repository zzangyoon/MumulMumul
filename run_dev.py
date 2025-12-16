from __future__ import annotations
import subprocess
import sys
import time
from typing import Optional


def _spawn_process(cmd: list[str]) -> subprocess.Popen:
    return subprocess.Popen(cmd)


def main() -> int:
    python = sys.executable

    uvicorn_cmd = [
        python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8022",
    ]

  

    print("Starting uvicorn and streamlit...")
    uvicorn_proc: Optional[subprocess.Popen] = None

    try:
        uvicorn_proc = _spawn_process(uvicorn_cmd)

        print(f"uvicorn PID: {uvicorn_proc.pid}")

        # Wait until one of them exits or we get KeyboardInterrupt
        while True:
            if uvicorn_proc.poll() is not None:
                print("uvicorn exited")
                break
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("Interrupted. Stopping processes...")

    return 0


if __name__ == "__main__":
    print("Hello from mumulmumul!")
    raise SystemExit(main())