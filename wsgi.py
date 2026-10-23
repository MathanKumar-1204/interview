import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask import Flask
from app import create_app

# Top-level Flask application instance for WSGI & Vercel
env = os.getenv("FLASK_ENV", "production")
app: Flask = create_app(env)

if __name__ == "__main__":
    app.run()
