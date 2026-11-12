import sys
import uvicorn
from backend.config import load_settings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

if __name__ == "__main__":
    settings = load_settings()
    host = settings.get("HOST", "0.0.0.0")
    port = settings.get("PORT", 8000)

    print("=" * 60)
    print("🚀  OTP Share Service Starting...")
    print(f"📡  Listening on: http://localhost:{port}")
    print(f"🌐  Network access: http://{host}:{port}")
    print("=" * 60)

    uvicorn.run("backend.app:app", host=host, port=port, reload=False)
