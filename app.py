import os
import sys
from pathlib import Path

# Add project root directory to sys.path so 'app' package resolves cleanly
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask import Flask
from app import create_app

# Top-level Flask application instance for Vercel and WSGI servers
env = os.getenv("FLASK_ENV", "production")
app: Flask = create_app(env)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"* Starting AI Interview Studio on port {port} (Debug: {debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
