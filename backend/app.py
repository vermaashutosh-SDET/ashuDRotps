import os
import json
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import database, config
from backend.mail_fetcher import fetcher_service, test_imap_connection, sse_subscribers, broadcast_event

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
    database.init_db()
    # Start background mail poller task
    poller_task = asyncio.create_task(fetcher_service.run_loop())
    yield
    # Shutdown
    fetcher_service.stop()
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="OTP Share Inbox", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ALLOWED_SERVICES = ["indiabulls", "dhani", "nsdl", "cdsl"]

def is_allowed_service(item):
    if not isinstance(item, dict):
        return False
    combined = f"{item.get('service_tag','')} {item.get('sender_name','')} {item.get('sender_email','')} {item.get('subject','')}".lower()
    return any(k in combined for k in ALLOWED_SERVICES)

def check_pin_auth(pin_header: Optional[str] = Header(None, alias="X-OTP-PIN")):
    cfg = config.load_settings()
    configured_pin = cfg.get("WEB_PIN", "").strip()
    if configured_pin:
        if not pin_header or pin_header.strip() != configured_pin:
            raise HTTPException(status_code=401, detail="Invalid or missing access PIN.")
    return True

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>OTP Share Frontend Missing</h1>", status_code=404)
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/stream")
async def sse_event_stream(request: Request):
    """Server-Sent Events endpoint to stream new OTPs and status in real-time."""
    queue = asyncio.Queue()
    sse_subscribers.add(queue)

    async def event_generator():
        # Send initial status
        init_status = fetcher_service.get_status_summary()
        yield f"event: status\ndata: {json.dumps(init_status)}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for next event or heartbeat timeout
                    item = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat keep-alive
                    yield ": ping\n\n"
        finally:
            sse_subscribers.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/api/status")
async def get_service_status():
    cfg = config.load_settings()
    status = fetcher_service.get_status_summary()
    status["has_pin"] = bool(cfg.get("WEB_PIN"))
    status["email_configured"] = bool(cfg.get("EMAIL_USER") and cfg.get("EMAIL_PASS"))
    status["phone_number"] = "7830531446"
    return status

@app.get("/api/otps")
async def list_otps(
    search: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    pin: Optional[str] = Header(None, alias="X-OTP-PIN")
):
    check_pin_auth(pin)
    cfg = config.load_settings()
    active_service = service
    if (not active_service or active_service.lower() == "all") and cfg.get("SENDER_FILTER"):
        active_service = cfg.get("SENDER_FILTER")

    otps = database.get_otps(limit=limit, search=search, service=active_service)
    otps = [x for x in otps if is_allowed_service(x)]
    latest = database.get_latest_otp(service=active_service)
    if latest and not is_allowed_service(latest):
        latest = otps[0] if otps else None
    return {
        "otps": otps,
        "latest": latest,
        "total": len(otps),
        "active_service": active_service
    }

@app.get("/api/otps/{otp_id}")
async def get_otp_detail(otp_id: int, pin: Optional[str] = Header(None, alias="X-OTP-PIN")):
    check_pin_auth(pin)
    item = database.get_otp_by_id(otp_id)
    if not item or not is_allowed_service(item):
        raise HTTPException(status_code=404, detail="OTP message not found.")
    return item

@app.delete("/api/otps/{otp_id}")
async def delete_otp_item(otp_id: int, pin: Optional[str] = Header(None, alias="X-OTP-PIN")):
    check_pin_auth(pin)
    success = database.delete_otp(otp_id)
    if not success:
        raise HTTPException(status_code=404, detail="OTP not found.")
    broadcast_event("deleted_otp", {"id": otp_id})
    return {"success": True, "id": otp_id}

@app.post("/api/otps/clear")
async def clear_all_otps(pin: Optional[str] = Header(None, alias="X-OTP-PIN")):
    check_pin_auth(pin)
    count = database.clear_all_otps()
    broadcast_event("cleared_all", {"count": count})
    return {"success": True, "cleared_count": count}

@app.post("/api/check-now")
async def trigger_check():
    new_items = await asyncio.to_thread(fetcher_service._sync_fetch_step)
    latest = database.get_latest_otp()
    return {"success": True, "new_count": len(new_items), "latest": latest}

class TestOTPRequest(BaseModel):
    service: Optional[str] = "Google"
    code: Optional[str] = None
    subject: Optional[str] = None

@app.post("/api/test-otp")
async def generate_test_otp(req: TestOTPRequest):
    """Inserts a mock OTP email for instant testing of UI, sounds, and live updates."""
    import random
    from datetime import datetime

    code = req.code or f"{random.randint(100000, 999999)}"
    service = req.service or "Google"
    services_map = {
        "Google": ("Google Accounts", "no-reply@accounts.google.com", f"G-{code} is your Google verification code"),
        "Netflix": ("Netflix Security", "info@mailer.netflix.com", f"Your Netflix temporary access code is {code}"),
        "Amazon": ("Amazon.com", "account-update@amazon.com", f"{code} is your Amazon OTP"),
        "GitHub": ("GitHub Support", "support@github.com", f"[{service}] Your two-factor code: {code}"),
        "HDFC Bank": ("HDFC NetBanking", "alerts@hdfcbank.net", f"OTP for your online transaction is {code}. Valid 5 mins.")
    }

    sender_name, sender_email, subject = services_map.get(
        service,
        (f"{service} Support", f"support@{service.lower().replace(' ', '')}.com", f"Your verification code is {code}")
    )

    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #1e293b; margin-top: 0;">Verification Code</h2>
        <p style="color: #475569; font-size: 15px;">Use the following verification code to complete your login or transaction:</p>
        <div style="background-color: #f1f5f9; padding: 16px; border-radius: 6px; text-align: center; margin: 20px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #0284c7;">{code}</span>
        </div>
        <p style="color: #64748b; font-size: 13px;">This code is valid for 10 minutes. If you did not request this, please ignore this email.</p>
    </div>
    """
    body_text = f"Your verification code is {code}. Do not share this code with anyone."
    import uuid
    dummy_mid = f"<test-{uuid.uuid4().hex[:12]}@local>"

    saved = database.insert_otp(
        message_id=dummy_mid,
        sender_name=sender_name,
        sender_email=sender_email,
        service_tag=service,
        subject=subject,
        otp_code=code,
        verification_link="https://accounts.google.com/verify?test=1",
        snippet=body_text,
        body_text=body_text,
        body_html=body_html,
        received_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    if saved:
        broadcast_event("new_otp", saved)
        return {"success": True, "otp": saved}
    return {"success": False, "message": "Failed to create test OTP"}

@app.get("/api/config")
async def get_configuration():
    cfg = config.load_settings()
    return {
        "EMAIL_USER": cfg["EMAIL_USER"],
        "EMAIL_PASS_SET": bool(cfg["EMAIL_PASS"]),
        "IMAP_HOST": cfg["IMAP_HOST"],
        "IMAP_PORT": cfg["IMAP_PORT"],
        "IMAP_FOLDER": cfg["IMAP_FOLDER"],
        "FILTER_KEYWORDS": cfg["FILTER_KEYWORDS_RAW"],
        "POLL_INTERVAL": cfg["POLL_INTERVAL"],
        "MARK_AS_READ": cfg["MARK_AS_READ"],
        "SENDER_FILTER": cfg.get("SENDER_FILTER", ""),
        "HAS_PIN": bool(cfg["WEB_PIN"]),
        "PORT": cfg["PORT"]
    }

class ConfigUpdateRequest(BaseModel):
    EMAIL_USER: Optional[str] = None
    EMAIL_PASS: Optional[str] = None
    IMAP_HOST: Optional[str] = None
    IMAP_PORT: Optional[int] = None
    IMAP_FOLDER: Optional[str] = None
    FILTER_KEYWORDS: Optional[str] = None
    POLL_INTERVAL: Optional[int] = None
    MARK_AS_READ: Optional[bool] = None
    SENDER_FILTER: Optional[str] = None
    WEB_PIN: Optional[str] = None

@app.post("/api/config")
async def update_configuration(req: ConfigUpdateRequest, pin: Optional[str] = Header(None, alias="X-OTP-PIN")):
    check_pin_auth(pin)

    updates = {}
    if req.EMAIL_USER is not None:
        updates["EMAIL_USER"] = req.EMAIL_USER.strip()
    if req.EMAIL_PASS is not None and req.EMAIL_PASS.strip():
        # Remove spaces in Google App Passwords (e.g. 'abcd efgh ijkl mnop' -> 'abcdefghijklmnop')
        updates["EMAIL_PASS"] = req.EMAIL_PASS.replace(" ", "").strip()
    if req.IMAP_HOST is not None:
        updates["IMAP_HOST"] = req.IMAP_HOST.strip()
    if req.IMAP_PORT is not None:
        updates["IMAP_PORT"] = req.IMAP_PORT
    if req.IMAP_FOLDER is not None:
        updates["IMAP_FOLDER"] = req.IMAP_FOLDER.strip()
    if req.FILTER_KEYWORDS is not None:
        updates["FILTER_KEYWORDS_RAW"] = req.FILTER_KEYWORDS.strip()
    if req.POLL_INTERVAL is not None:
        updates["POLL_INTERVAL"] = max(2, req.POLL_INTERVAL)
    if req.MARK_AS_READ is not None:
        updates["MARK_AS_READ"] = req.MARK_AS_READ
    if req.SENDER_FILTER is not None:
        updates["SENDER_FILTER"] = req.SENDER_FILTER.strip()
    if req.WEB_PIN is not None:
        updates["WEB_PIN"] = req.WEB_PIN.strip()

    config.save_settings(updates)
    fetcher_service.trigger_check()
    return {"success": True, "message": "Settings saved successfully."}

class TestConnectionRequest(BaseModel):
    EMAIL_USER: Optional[str] = ""
    EMAIL_PASS: Optional[str] = ""
    IMAP_HOST: Optional[str] = "imap.gmail.com"
    IMAP_PORT: Optional[int] = 993

@app.post("/api/test-connection")
async def test_connection_endpoint(req: TestConnectionRequest):
    cfg = config.load_settings()
    user = (req.EMAIL_USER or "").strip() or cfg.get("EMAIL_USER", "")
    raw_pass = (req.EMAIL_PASS or "").strip() or cfg.get("EMAIL_PASS", "")
    clean_pass = raw_pass.replace(" ", "").strip()
    host = (req.IMAP_HOST or "").strip() or cfg.get("IMAP_HOST", "imap.gmail.com")
    port = req.IMAP_PORT or cfg.get("IMAP_PORT", 993)

    if not user:
        return {"success": False, "message": "Email address is required."}
    if not clean_pass:
        return {"success": False, "message": "App Password is required. Please enter your 16-character App Password."}

    # Run blocking IMAP operation safely in worker thread
    result = await asyncio.to_thread(
        test_imap_connection,
        user=user,
        password=clean_pass,
        host=host,
        port=port
    )
    return result
