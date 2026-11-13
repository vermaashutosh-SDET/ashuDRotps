import os
import sys
import email
import imaplib
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse, Response
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
API_DIR = Path(__file__).resolve().parent
for p in [str(BASE_DIR), str(API_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    import parser
except ImportError:
    from backend import parser

from backend.config import load_settings

app = FastAPI(title="OTP Share Vercel")

# In-memory store for serverless instance
memory_cache = {
    "otps": [],
    "last_fetch": 0
}

ALLOWED_SERVICES = ["indiabulls", "dhani", "nsdl", "cdsl"]

def is_allowed_service(item):
    if not isinstance(item, dict):
        return False
    combined = f"{item.get('service_tag','')} {item.get('sender_name','')} {item.get('sender_email','')} {item.get('subject','')}".lower()
    return any(k in combined for k in ALLOWED_SERVICES)

def check_pin_auth(pin: Optional[str]):
    cfg = load_settings()
    required_pin = cfg.get("WEB_PIN") or os.getenv("WEB_PIN", "")
    if required_pin and pin != required_pin:
        raise HTTPException(status_code=401, detail="PIN required or invalid")

def fetch_from_gmail(force: bool = False):
    """Fetch latest OTP emails directly from Gmail via IMAP on-demand with caching."""
    import time
    now_ts = time.time()
    if not force and memory_cache["otps"] and (now_ts - memory_cache.get("last_fetch", 0) < 3.0):
        return memory_cache["otps"]

    cfg = load_settings()
    user = os.getenv("EMAIL_USER") or cfg.get("EMAIL_USER")
    password = os.getenv("EMAIL_PASS") or cfg.get("EMAIL_PASS")
    host = os.getenv("IMAP_HOST") or cfg.get("IMAP_HOST", "imap.gmail.com")
    port = int(os.getenv("IMAP_PORT") or cfg.get("IMAP_PORT", 993))
    sender_filter = os.getenv("SENDER_FILTER") or cfg.get("SENDER_FILTER", "indiabulls,dhani")
    keywords = cfg.get("FILTER_KEYWORDS", ["otp", "verification", "code", "login", "security", "one-time", "verify"])

    if not user or not password:
        return []

    client = None
    results = []
    try:
        client = imaplib.IMAP4_SSL(host, port, timeout=8)
        client.login(user, password)
        client.select("INBOX", readonly=True)

        # Build robust IMAP search criteria that captures Indiabulls, Dhani, and NSDL / Demat mandate OTPs
        terms = [s.strip().lower() for s in sender_filter.split(",") if s.strip()]
        if any(t in ["indiabulls", "dhani"] for t in terms) and "nsdl" not in terms:
            terms.extend(["nsdl", "cdsl"])

        search_criteria = 'OR (OR FROM indiabulls FROM dhani) (OR (OR FROM nsdl FROM cdsl) SUBJECT indiabulls)'

        status, data = client.search(None, search_criteria)
        if status == "OK" and data and data[0]:
            matching_seqs = data[0].split()[-8:]
            for seq_bytes in reversed(matching_seqs):
                seq = seq_bytes.decode()
                try:
                    s_res, m_data = client.fetch(seq, "(RFC822)")
                    if s_res == "OK" and m_data and isinstance(m_data[0], tuple):
                        parsed = parser.parse_email_message(m_data[0][1], keywords, terms)
                        if parsed and is_allowed_service(parsed):
                            parsed["id"] = int(seq)
                            results.append(parsed)
                except Exception:
                    continue

        client.logout()
        memory_cache["otps"] = [x for x in results if is_allowed_service(x)]
        memory_cache["last_fetch"] = time.time()
    except Exception as e:
        if client:
            try:
                client.logout()
            except Exception:
                pass
        print(f"IMAP on-demand error: {e}")

    return [x for x in results if is_allowed_service(x)]

@app.get("/", response_class=HTMLResponse)
async def serve_home():
    for p in [Path(__file__).resolve().parent / "index.html", BASE_DIR / "index.html", BASE_DIR / "static" / "index.html"]:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return HTMLResponse(content=f.read())
            except Exception:
                pass
    return HTMLResponse(content="<h1>OTP Share Dashboard</h1>")

@app.get("/api/status")
@app.get("/status")
async def get_status():
    cfg = load_settings()
    user = os.getenv("EMAIL_USER") or cfg.get("EMAIL_USER", "")
    return {
        "status": "connected" if user else "unconfigured",
        "monitored_email": user,
        "phone_number": "7830531446",
        "unread_count": 0,
        "connected": bool(user),
        "has_pin": bool(os.getenv("WEB_PIN") or cfg.get("WEB_PIN")),
        "email_configured": bool(user)
    }

@app.get("/api/otps")
@app.get("/otps")
async def get_otps(
    service: Optional[str] = Query(None),
    pin: Optional[str] = Header(None, alias="X-OTP-PIN")
):
    check_pin_auth(pin)
    fetched = fetch_from_gmail()
    if fetched:
        memory_cache["otps"] = [x for x in fetched if is_allowed_service(x)]

    # Strictly lock down: Only Indiabulls, Dhani, and NSDL / CDSL can ever be returned
    items = [x for x in memory_cache["otps"] if is_allowed_service(x)]
    if service and service.lower() not in ["all", ""]:
        items = [x for x in items if service.lower() in f"{x.get('service_tag','')} {x.get('sender_name','')} {x.get('subject','')}".lower()]

    latest = items[0] if items else None
    return {
        "otps": items,
        "latest": latest,
        "total": len(items)
    }

@app.get("/api/otps/{otp_id}")
@app.get("/otps/{otp_id}")
async def get_otp_detail(otp_id: int, pin: Optional[str] = Header(None, alias="X-OTP-PIN")):
    check_pin_auth(pin)
    for item in memory_cache["otps"]:
        if item.get("id") == otp_id and is_allowed_service(item):
            return item
    fetched = fetch_from_gmail()
    if fetched:
        memory_cache["otps"] = [x for x in fetched if is_allowed_service(x)]
        for item in memory_cache["otps"]:
            if item.get("id") == otp_id and is_allowed_service(item):
                return item
    raise HTTPException(status_code=404, detail="OTP message not found.")

@app.delete("/api/otps/{otp_id}")
@app.delete("/otps/{otp_id}")
async def delete_otp_item(otp_id: int, pin: Optional[str] = Header(None, alias="X-OTP-PIN")):
    check_pin_auth(pin)
    memory_cache["otps"] = [x for x in memory_cache["otps"] if x.get("id") != otp_id]
    return {"success": True, "id": otp_id}

@app.post("/api/otps/clear")
@app.post("/otps/clear")
async def clear_all_otps(pin: Optional[str] = Header(None, alias="X-OTP-PIN")):
    check_pin_auth(pin)
    count = len(memory_cache["otps"])
    memory_cache["otps"] = []
    return {"success": True, "cleared_count": count}

@app.post("/api/check-now")
@app.post("/check-now")
async def check_now(pin: Optional[str] = Header(None, alias="X-OTP-PIN")):
    check_pin_auth(pin)
    fetched = fetch_from_gmail(force=True)
    if fetched:
        memory_cache["otps"] = fetched
    return {"success": True, "new_count": len(fetched), "latest": fetched[0] if fetched else None}

@app.get("/api/config")
@app.get("/config")
async def get_config():
    cfg = load_settings()
    return {
        "EMAIL_USER": os.getenv("EMAIL_USER") or cfg.get("EMAIL_USER", ""),
        "EMAIL_PASS_SET": bool(os.getenv("EMAIL_PASS") or cfg.get("EMAIL_PASS")),
        "IMAP_HOST": os.getenv("IMAP_HOST") or cfg.get("IMAP_HOST", "imap.gmail.com"),
        "IMAP_PORT": int(os.getenv("IMAP_PORT") or cfg.get("IMAP_PORT", 993)),
        "IMAP_FOLDER": "INBOX",
        "FILTER_KEYWORDS": "otp,verification,code,login,security,one-time,verify",
        "POLL_INTERVAL": 5,
        "MARK_AS_READ": False,
        "SENDER_FILTER": os.getenv("SENDER_FILTER") or cfg.get("SENDER_FILTER", "indiabulls,dhani"),
        "WEB_PIN": os.getenv("WEB_PIN") or cfg.get("WEB_PIN", "")
    }

@app.get("/api/stream")
@app.get("/stream")
async def sse_stream():
    async def event_generator():
        yield f"event: status\ndata: {{\"status\": \"connected\"}}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

class TestOTPRequest(BaseModel):
    service: Optional[str] = "Indiabulls"
    code: Optional[str] = None

@app.post("/api/test-otp")
@app.post("/test-otp")
async def test_otp(req: TestOTPRequest):
    import random
    from datetime import datetime
    code = req.code or str(random.randint(100000, 999999))
    service = req.service or "Indiabulls"
    dummy = {
        "id": 999999,
        "message_id": "<test-vercel@local>",
        "sender_name": f"{service} Support",
        "sender_email": f"stocksotp@{service.lower()}.com",
        "service_tag": service,
        "subject": f"Your OTP for secure Login on {service}",
        "otp_code": code,
        "verification_link": None,
        "snippet": f"Your verification code is {code}. Do not share with anyone.",
        "body_text": f"Your verification code is {code}.",
        "body_html": f"<h2>Your {service} OTP is: <b>{code}</b></h2>",
        "received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    memory_cache["otps"].insert(0, dummy)
    return {"success": True, "otp": dummy}

@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path_name: str):
    endpoint = (request.query_params.get("endpoint") or "").lower()
    path = request.url.path.lower()

    if "style.css" in path or "style.css" in endpoint:
        for p in [Path(__file__).resolve().parent / "style.css", BASE_DIR / "static" / "style.css"]:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    return Response(content=f.read(), media_type="text/css")
        return Response(content="", media_type="text/css")

    if "app.js" in path or "app.js" in endpoint:
        for p in [Path(__file__).resolve().parent / "app.js", BASE_DIR / "static" / "app.js"]:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    return Response(content=f.read(), media_type="application/javascript")
        return Response(content="", media_type="application/javascript")

    if "otps/" in endpoint or "otps/" in path:
        import re
        m = re.search(r"otps/(\d+)", endpoint or path)
        if m:
            oid = int(m.group(1))
            if request.method == "DELETE":
                return await delete_otp_item(oid)
            else:
                return await get_otp_detail(oid)
    elif "otps/clear" in endpoint or "otps/clear" in path:
        return await clear_all_otps()
    elif "status" in endpoint or path.endswith("/status"):
        return await get_status()
    elif "otps" in endpoint or "otps" in path:
        service = request.query_params.get("service")
        pin = request.headers.get("x-otp-pin")
        return await get_otps(service=service, pin=pin)
    elif "config" in endpoint or path.endswith("/config"):
        return await get_config()
    elif "check-now" in endpoint or path.endswith("/check-now"):
        pin = request.headers.get("x-otp-pin")
        return await check_now(pin=pin)
    elif "test-otp" in endpoint or path.endswith("/test-otp"):
        try:
            body = await request.json()
            return await test_otp(TestOTPRequest(**body))
        except Exception:
            return await test_otp(TestOTPRequest())
    elif "stream" in endpoint or path.endswith("/stream"):
        return await sse_stream()

    # Default to serving the HTML dashboard
    return await serve_home()
