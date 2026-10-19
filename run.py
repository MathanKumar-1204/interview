import os
from app import create_app

env = os.getenv("FLASK_ENV", "development")
app = create_app(env)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    print(f"* AI Interview Studio starting on http://localhost:{port} (Debug: {debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
