import os
import sys
import traceback
from app import create_app

try:
    env = os.getenv("FLASK_ENV", "production")
    app = create_app(env)
except Exception as exc:
    err_trace = traceback.format_exc()
    print(f"[Startup Error] {err_trace}", file=sys.stderr)
    from flask import Flask, Response

    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def startup_error(path):
        return Response(f"<pre>{err_trace}</pre>", status=500, mimetype="text/html")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"* Starting AI Interview Studio on port {port} (Debug: {debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
