import os
import sys
from pathlib import Path

# Add project root directory to sys.path so 'app' package resolves cleanly on Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import os
import sys
import traceback
from pathlib import Path

# Add project root directory to sys.path so 'app' package resolves cleanly on Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Vercel WSGI entrypoint with startup error diagnostics
try:
    from app import create_app
    env = os.getenv("FLASK_ENV", "production")
    app = create_app(env)
except Exception as exc:
    err_trace = traceback.format_exc()
    print(f"[Vercel Startup Error] {err_trace}", file=sys.stderr)
    from flask import Flask, Response

    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def startup_error(path):
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Application Startup Error - AI Interview Studio</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2.5rem; }}
    .container {{ max-width: 820px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 2rem; border: 1px solid #334155; }}
    h1 {{ color: #ef4444; margin-top: 0; font-size: 1.5rem; }}
    p {{ color: #94a3b8; font-size: 0.95rem; line-height: 1.6; }}
    pre {{ background: #0b1120; color: #fca5a5; padding: 1.25rem; border-radius: 8px; overflow-x: auto; font-size: 0.85rem; border: 1px solid #7f1d1d; }}
    .tip {{ background: #172554; border-left: 4px solid #3b82f6; padding: 1rem; border-radius: 6px; margin-top: 1.5rem; color: #bfdbfe; font-size: 0.875rem; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>⚠️ Application Startup Error on Vercel</h1>
    <p>The AI Interview Studio failed to initialize during serverless boot. Review the traceback below:</p>
    <pre>{err_trace}</pre>
    <div class="tip">
      💡 <b>Troubleshooting:</b> Ensure all required environment variables (e.g. <code>MONGO_URI</code>, <code>SECRET_KEY</code>, <code>GEMINI_API_KEY</code>) are configured in the Vercel Project Settings under <b>Settings &rarr; Environment Variables</b>.
    </div>
  </div>
</body>
</html>"""
        return Response(html, status=500, mimetype="text/html")
