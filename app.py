import os
from app import create_app

env = os.getenv("FLASK_ENV", "production")
app = create_app(env)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"* Starting AI Interview Studio on port {port} (Debug: {debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
