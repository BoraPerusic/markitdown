from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional

import uvicorn

from .config import load_config
from .app import create_app


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Run the MarkItDown Web server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to markitdown_web.toml (default: ./markitdown_web.toml or MARKITDOWN_WEB_CONFIG)",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)

    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))

    app = create_app(cfg)
    uvicorn.run(app, host=args.host, port=args.port, log_level=cfg.log_level)


if __name__ == "__main__":
    main(sys.argv[1:])
