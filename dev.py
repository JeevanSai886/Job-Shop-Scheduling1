"""Start both local services; Ctrl+C shuts them down. Run from the project's virtual environment."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    node = shutil.which("node")
    vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite.exists():
        raise SystemExit("Install Node.js and run pnpm install in frontend before starting the app.")
    children: list[subprocess.Popen] = []
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                cwd=ROOT,
                **options,
            )
        )
        children.append(
            subprocess.Popen([node, str(vite), "--host", "127.0.0.1"], cwd=ROOT / "frontend", **options)
        )
        print("Sequence: http://127.0.0.1:5173 · API docs: http://127.0.0.1:8000/docs", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise SystemExit("A service exited. Check its output above.")
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
