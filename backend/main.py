"""Simple backend runner for local development."""

from __future__ import annotations

import argparse
from importlib.util import find_spec
import os
from pathlib import Path
import socket
import subprocess
import sys

import uvicorn


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ET backend API")
    parser.add_argument("--host", default=os.getenv("API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("API_PORT", "8000")))
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )
    return parser


def _project_python_path() -> Path:
    backend_dir = Path(__file__).resolve().parent
    repo_dir = backend_dir.parent
    if os.name == "nt":
        candidates = [
            backend_dir / "venv" / "Scripts" / "python.exe",
            repo_dir / ".venv" / "Scripts" / "python.exe",
        ]
    else:
        candidates = [
            backend_dir / "venv" / "bin" / "python",
            repo_dir / ".venv" / "bin" / "python",
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def _relaunch_with_project_python_if_needed() -> None:
    target_python = _project_python_path()
    if not target_python.exists():
        return

    current_python = Path(sys.executable).resolve()
    if current_python == target_python.resolve():
        return

    print(f"Switching to project Python interpreter: {target_python}")
    os.execv(
        str(target_python),
        [str(target_python), str(Path(__file__).resolve()), *sys.argv[1:]],
    )


def _ensure_dependencies_installed() -> None:
    required_modules = ["fastapi", "dotenv", "langchain_google_genai", "uvicorn"]
    missing = [module for module in required_modules if find_spec(module) is None]
    if not missing:
        return

    requirements_path = Path(__file__).resolve().parent / "requirements.txt"
    print(
        f"Missing dependencies detected ({', '.join(missing)}). "
        "Installing from requirements.txt..."
    )

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)],
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit("Failed to install required dependencies.")


def _find_available_port(host: str, preferred_port: int, max_attempts: int = 20) -> int:
    for offset in range(max_attempts + 1):
        candidate = preferred_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue

    raise SystemExit(
        f"No available port found starting at {preferred_port}. "
        "Pass --port with a different value."
    )


def _run_server(host: str, port: int, reload: bool) -> None:
    # Let uvicorn manage signal handling so Ctrl+C prints normal shutdown logs.
    try:
        uvicorn.run("api.main:app", host=host, port=port, reload=reload)
    except KeyboardInterrupt:
        pass


def main() -> None:
    _relaunch_with_project_python_if_needed()
    args = _build_parser().parse_args()
    _ensure_dependencies_installed()
    selected_port = _find_available_port(args.host, args.port)
    if selected_port != args.port:
        print(f"Port {args.port} is busy. Using port {selected_port} instead.")

    _run_server(args.host, selected_port, args.reload)


if __name__ == "__main__":
    main()
