import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

def load_settings():
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=True)
    return {
        "EMAIL_USER": os.getenv("EMAIL_USER", "").strip(),
        "EMAIL_PASS": os.getenv("EMAIL_PASS", "").strip(),
        "IMAP_HOST": os.getenv("IMAP_HOST", "imap.gmail.com").strip(),
        "IMAP_PORT": int(os.getenv("IMAP_PORT", "993").strip() or 993),
        "IMAP_FOLDER": os.getenv("IMAP_FOLDER", "INBOX").strip() or "INBOX",
        "FILTER_KEYWORDS": [
            k.strip().lower()
            for k in os.getenv("FILTER_KEYWORDS", "otp,verification,code,login,security,one-time,verify,auth,pin").split(",")
            if k.strip()
        ],
        "FILTER_KEYWORDS_RAW": os.getenv("FILTER_KEYWORDS", "otp,verification,code,login,security,one-time,verify,auth,pin"),
        "POLL_INTERVAL": max(2, int(os.getenv("POLL_INTERVAL", "5").strip() or 5)),
        "MARK_AS_READ": os.getenv("MARK_AS_READ", "false").strip().lower() in ("true", "1", "yes"),
        "SENDER_FILTER": os.getenv("SENDER_FILTER", "").strip(),
        "SENDER_FILTER_LIST": [
            s.strip().lower()
            for s in os.getenv("SENDER_FILTER", "").split(",")
            if s.strip()
        ],
        "WEB_PIN": os.getenv("WEB_PIN", "").strip(),
        "PORT": int(os.getenv("PORT", "8000").strip() or 8000),
        "HOST": os.getenv("HOST", "0.0.0.0").strip() or "0.0.0.0",
    }

def save_settings(new_settings: dict):
    """Update .env file with new settings while preserving comments and structure."""
    settings = load_settings()
    settings.update(new_settings)

    lines = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    keys_to_update = {
        "EMAIL_USER": settings.get("EMAIL_USER", ""),
        "EMAIL_PASS": settings.get("EMAIL_PASS", ""),
        "IMAP_HOST": settings.get("IMAP_HOST", "imap.gmail.com"),
        "IMAP_PORT": str(settings.get("IMAP_PORT", 993)),
        "IMAP_FOLDER": settings.get("IMAP_FOLDER", "INBOX"),
        "FILTER_KEYWORDS": settings.get("FILTER_KEYWORDS_RAW", "otp,verification,code,login,security,one-time,verify,auth,pin"),
        "POLL_INTERVAL": str(settings.get("POLL_INTERVAL", 5)),
        "MARK_AS_READ": "true" if settings.get("MARK_AS_READ") else "false",
        "SENDER_FILTER": settings.get("SENDER_FILTER", ""),
        "WEB_PIN": settings.get("WEB_PIN", ""),
        "PORT": str(settings.get("PORT", 8000)),
        "HOST": settings.get("HOST", "0.0.0.0"),
    }

    updated_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in keys_to_update:
                new_lines.append(f"{key}={keys_to_update[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Append any keys that weren't in the original file
    for key, val in keys_to_update.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return load_settings()
