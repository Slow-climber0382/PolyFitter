#!/usr/bin/env python3
"""Launch the local PolyFitter 3D Web Studio."""
from __future__ import annotations

import argparse
from pathlib import Path
import socket
import threading
import time
import webbrowser

import uvicorn

from core.contracts import Vec3
from web.server import create_app


def _parse_rot(raw: str) -> Vec3:
    parts = [float(p.strip()) for p in raw.split(",")]
    if len(parts) != 3:
        raise ValueError(f"--rotation requires 3 numbers x,y,z, got {raw!r}")
    return Vec3(*parts)


def _find_available_port(host: str, start_port: int, max_tries: int = 20) -> int:
    for offset in range(max_tries):
        candidate = start_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex((host, candidate)) != 0:
                return candidate
    return start_port


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start PolyFitter 3D Web GUI")
    parser.add_argument("helmet", type=Path, nargs="?", default=None, help="Optional initial .stl/.obj file")
    parser.add_argument("--rotation", type=str, default="0,0,0", help="Initial rotation x,y,z in degrees")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Preferred start port (default: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser tab")
    args = parser.parse_args(argv)

    port = _find_available_port(args.host, args.port)
    app = create_app(initial_helmet=args.helmet, initial_rotation=_parse_rot(args.rotation))
    url = f"http://{args.host}:{port}"
    print(f"PolyFitter 3D Studio działa pod adresem: {url}")

    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)), daemon=True).start()

    uvicorn.run(app, host=args.host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
