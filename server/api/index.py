"""
Vercel Serverless Entry Point

Vercel's Python runtime looks for a variable named `app` (or `handler`)
in api/index.py. We import the FastAPI app from server.py and expose it here.

All routes defined in server.py are automatically available.
"""

import sys
from pathlib import Path

# Add the server directory to Python path so imports (db, agent_invoker, etc.) resolve
_server_dir = str(Path(__file__).resolve().parent.parent)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from server import app

