"""Start the app:  python run.py   then open http://localhost:8000"""
from app.config import settings
from app.server import app

if __name__ == "__main__":
    print(f"Loyalty Advisor  provider={settings.provider()}  model={settings.model}  mode={settings.mode}")
    if settings.provider() == "none":
        print("WARNING: no API key found. Add PORTKEY_API_KEY to a .env file (here or one folder up).")
    print(f"Open http://localhost:{settings.port}")
    app.run(host="127.0.0.1", port=settings.port, threaded=True)
