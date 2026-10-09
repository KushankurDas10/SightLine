"""Pytest configuration and common fixtures."""

import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

# Ensure SightLine root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Set default MOCK environment for fast tests
os.environ.setdefault("MOCK", "1")

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_server():
    """Serve tests/fixtures on localhost with ALLOW_PRIVATE_URLS=1."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURES_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    _, port = server.server_address

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    old_allow = os.environ.get("ALLOW_PRIVATE_URLS")
    os.environ["ALLOW_PRIVATE_URLS"] = "1"

    base_url = f"http://127.0.0.1:{port}"
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        if old_allow is not None:
            os.environ["ALLOW_PRIVATE_URLS"] = old_allow
        else:
            os.environ.pop("ALLOW_PRIVATE_URLS", None)
