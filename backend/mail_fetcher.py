import imaplib
import time
import logging
import asyncio
import threading
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from backend import database, parser
from backend.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MailFetcher")

# Global SSE subscriber queues
sse_subscribers: Set[asyncio.Queue] = set()

def broadcast_event(event_type: str, data: Any):
    """Pushes an event to all connected SSE clients."""
    payload = {"event": event_type, "data": data}
    for queue in list(sse_subscribers):
        try:
            queue.put_nowait(payload)
        except Exception:
            pass

def test_imap_connection(user: str, password: str, host: str, port: int) -> Dict[str, Any]:
    """Tests IMAP credentials and returns connection status."""
    user = (user or "").strip()
    password = (password or "").replace(" ", "").strip()
    host = (host or "imap.gmail.com").strip()
    port = int(port or 993)

    if not user:
        return {"success": False, "message": "Email address is required."}
    if not password:
        return {"success": False, "message": "App Password is required. Please enter your 16-character App Password."}

    user_lower = user.lower()

    # Auto-fix host if user entered email or left host blank
    if "@" in host or not host:
        if "@outlook." in host.lower() or "@outlook." in user_lower or "@hotmail." in user_lower or "@live." in user_lower:
            host = "outlook.office365.com"
        elif "@yahoo." in host.lower() or "@yahoo." in user_lower:
            host = "imap.mail.yahoo.com"
        elif "@icloud." in host.lower() or "@icloud." in user_lower or "@me.com" in user_lower:
            host = "imap.mail.me.com"
        else:
            host = "imap.gmail.com"

    # Auto-adjust host if email provider is obvious
    if host in ("imap.gmail.com", ""):
        if "@outlook." in user_lower or "@hotmail." in user_lower or "@live." in user_lower:
            host = "outlook.office365.com"
        elif "@yahoo." in user_lower:
            host = "imap.mail.yahoo.com"
        elif "@icloud." in user_lower or "@me.com" in user_lower:
            host = "imap.mail.me.com"

    client = None
    try:
        # Connect with SSL timeout of 10 seconds
        client = imaplib.IMAP4_SSL(host, port, timeout=10)
        typ, auth_response = client.login(user, password)
        if typ != "OK":
            return {"success": False, "message": f"Login failed: {auth_response}"}

        # Verify folder listing
        typ, folders = client.list()
        folder_names = []
        if typ == "OK" and folders:
            for f in folders:
                try:
                    f_str = f.decode("utf-8", errors="ignore")
                    name = f_str.split('"')[-2] if '"' in f_str else f_str.split()[-1]
                    if name and not name.startswith("\\"):
                        folder_names.append(name)
                except Exception:
                    pass

        # Try selecting INBOX
        typ, data = client.select("INBOX", readonly=True)
        total_inbox = data[0].decode() if (data and data[0]) else "0"

        return {
            "success": True,
            "message": f"Successfully connected to {host} as {user}! (INBOX has {total_inbox} messages)",
            "folders": folder_names[:8]
        }
    except imaplib.IMAP4.error as e:
        err_msg = str(e)
        err_lower = err_msg.lower()
        if "authenticationfailed" in err_lower or "invalid credentials" in err_lower:
            return {
                "success": False,
                "message": "Authentication failed! Make sure you use a 16-character App Password (not your normal Gmail password). In Google, generate one at https://myaccount.google.com/apppasswords with 2-Step Verification ON."
            }
        if "application-specific password" in err_lower:
            return {
                "success": False,
                "message": "Google requires an App Password for IMAP. Generate a 16-character code at https://myaccount.google.com/apppasswords"
            }
        return {"success": False, "message": f"IMAP Authentication Error: {err_msg}"}
    except Exception as e:
        err_str = str(e)
        err_lower = err_str.lower()
        if "timed out" in err_lower:
            return {
                "success": False,
                "message": f"Connection timed out reaching {host}:{port}. Please verify the host and your network connection."
            }
        if "getaddrinfo failed" in err_lower or "name or service not known" in err_lower:
            return {
                "success": False,
                "message": f"Could not find host '{host}'. Please check the IMAP server name."
            }
        return {"success": False, "message": f"Connection error: {err_str}"}
    finally:
        if client:
            try:
                client.logout()
            except Exception:
                pass


class MailFetcherService:
    def __init__(self):
        self.running = False
        self.status = "unconfigured"
        self.last_check: Optional[str] = None
        self.last_error: Optional[str] = None
        self.monitored_email: str = ""
        self.unread_count: int = 0
        self.total_fetched: int = 0
        self.client: Optional[imaplib.IMAP4_SSL] = None
        self.connected_creds: Optional[tuple] = None
        self.last_total_msgs: int = 0
        self.wake_event = asyncio.Event()
        self.fetch_lock = threading.Lock()

    def get_status_summary(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "monitored_email": self.monitored_email,
            "last_check": self.last_check,
            "last_error": self.last_error,
            "unread_count": self.unread_count,
            "total_fetched": self.total_fetched,
            "connected": self.status in ("connected", "idle", "polling")
        }

    def trigger_check(self):
        """Signals background poller to check immediately."""
        self.wake_event.set()

    def _disconnect_client(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            try:
                self.client.logout()
            except Exception:
                pass
        self.client = None
        self.connected_creds = None

    def _ensure_connected(self, user, password, host, port, folder, mark_as_read) -> imaplib.IMAP4_SSL:
        creds = (user, password, host, port, folder)
        if self.client and self.connected_creds == creds:
            try:
                # Fast heartbeat check
                typ, _ = self.client.noop()
                if typ == "OK":
                    return self.client
            except Exception:
                self._disconnect_client()

        # Connect new persistent SSL session
        self._disconnect_client()
        client = imaplib.IMAP4_SSL(host, port, timeout=12)
        typ, auth_resp = client.login(user, password)
        if typ != "OK":
            raise Exception(f"Login failed: {auth_resp}")

        typ, _ = client.select(f'"{folder}"', readonly=(not mark_as_read))
        if typ != "OK":
            client.select("INBOX", readonly=(not mark_as_read))

        self.client = client
        self.connected_creds = creds
        return self.client

    def _sync_fetch_step(self) -> List[Dict[str, Any]]:
        """Thread-safe entry point for fetching OTPs."""
        if not self.fetch_lock.acquire(blocking=True, timeout=8):
            return []
        try:
            return self._locked_sync_fetch()
        finally:
            self.fetch_lock.release()

    def _locked_sync_fetch(self) -> List[Dict[str, Any]]:
        """Fast, persistent IMAP check. Uses cached connection for sub-second responses."""
        import re
        cfg = load_settings()
        user = cfg["EMAIL_USER"]
        password = cfg["EMAIL_PASS"]
        host = cfg["IMAP_HOST"]
        port = cfg["IMAP_PORT"]
        folder = cfg["IMAP_FOLDER"]
        keywords = cfg["FILTER_KEYWORDS"]
        mark_as_read = cfg["MARK_AS_READ"]
        sender_filter = cfg.get("SENDER_FILTER_LIST", [])

        self.monitored_email = user

        if not user or not password:
            self.status = "unconfigured"
            self.last_error = "Email address or App Password is not configured."
            return []

        # Auto-heal host if it contains @ or is empty
        if "@" in host or not host:
            user_lower = user.lower()
            if "@outlook." in host.lower() or "@outlook." in user_lower or "@hotmail." in user_lower:
                host = "outlook.office365.com"
            elif "@yahoo." in host.lower() or "@yahoo." in user_lower:
                host = "imap.mail.yahoo.com"
            elif "@icloud." in host.lower() or "@icloud." in user_lower or "@me.com" in user_lower:
                host = "imap.mail.me.com"
            else:
                host = "imap.gmail.com"

        self.status = "polling"
        new_items = []

        try:
            client = self._ensure_connected(user, password, host, port, folder, mark_as_read)

            # Check status of mailbox (takes < 0.3s over persistent connection!)
            typ, status_data = client.status(f'"{folder}"', '(MESSAGES UNSEEN)')
            if typ != "OK" or not status_data:
                # Re-select folder
                typ, _ = client.select(f'"{folder}"', readonly=(not mark_as_read))
                typ, status_data = client.status(f'"{folder}"', '(MESSAGES UNSEEN)')

            raw_status = status_data[0].decode("utf-8", errors="ignore") if status_data else ""
            m = re.search(r'MESSAGES\s+(\d+)\s+UNSEEN\s+(\d+)', raw_status)
            total_msgs = int(m.group(1)) if m else 0
            unseen_count = int(m.group(2)) if m else 0
            self.unread_count = unseen_count

            target_ids = []

            if self.last_total_msgs == 0:
                # First run: inspect last 15 messages so recent mailbox is ready
                if total_msgs > 0:
                    start_seq = max(1, total_msgs - 15)
                    target_ids = [str(i).encode() for i in range(start_seq, total_msgs + 1)]
                self.last_total_msgs = total_msgs
            elif total_msgs > self.last_total_msgs:
                # NEW EMAIL(S) ARRIVED! Inspect only the newly delivered sequence numbers
                target_ids = [str(i).encode() for i in range(self.last_total_msgs + 1, total_msgs + 1)]
                logger.info(f"⚡ New email detected! Fetching message sequences: {self.last_total_msgs + 1} to {total_msgs}")
                self.last_total_msgs = total_msgs
            else:
                # Same count, check if unseen messages exist that we might not have in DB
                self.last_total_msgs = total_msgs

            # Sort descending (newest first)
            sorted_ids = sorted(list(target_ids), key=lambda x: int(x), reverse=True)

            for msg_id in sorted_ids:
                try:
                    # Fast check: Fetch Message-ID header first to avoid downloading body if seen
                    typ, header_data = client.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
                    if typ == "OK" and header_data and header_data[0] and isinstance(header_data[0], tuple):
                        header_raw = header_data[0][1].decode("utf-8", errors="ignore")
                        if "Message-ID:" in header_raw:
                            mid_val = header_raw.split("Message-ID:", 1)[1].strip()
                            if mid_val and database.is_message_seen(mid_val):
                                continue

                    # Fetch full RFC822 message
                    typ, msg_data = client.fetch(msg_id, "(BODY.PEEK[])")
                    if typ != "OK" or not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple):
                        continue

                    raw_bytes = msg_data[0][1]
                    parsed = parser.parse_email_message(raw_bytes, keywords, sender_filter=sender_filter)
                    if not parsed:
                        continue

                    # Insert into DB
                    saved = database.insert_otp(
                        message_id=parsed["message_id"],
                        sender_name=parsed["sender_name"],
                        sender_email=parsed["sender_email"],
                        service_tag=parsed["service_tag"],
                        subject=parsed["subject"],
                        otp_code=parsed["otp_code"],
                        verification_link=parsed["verification_link"],
                        snippet=parsed["snippet"],
                        body_text=parsed["body_text"],
                        body_html=parsed["body_html"],
                        received_at=parsed["received_at"]
                    )

                    if saved:
                        new_items.append(saved)
                        self.total_fetched += 1
                        logger.info(f"⚡ Live OTP captured: {saved['service_tag']} -> {saved['otp_code']}")
                        broadcast_event("new_otp", saved)

                        if mark_as_read:
                            try:
                                client.store(msg_id, "+FLAGS", "\\Seen")
                            except Exception:
                                pass
                except Exception as ex:
                    logger.warning(f"Error fetching msg {msg_id}: {ex}")

            self.status = "connected"
            self.last_check = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.last_error = None
            return new_items

        except Exception as e:
            self.status = "error"
            self.last_error = f"Connection error: {str(e)}"
            self._disconnect_client()
            return []

    async def run_loop(self):
        """Asynchronous poller loop running every 2 seconds for true real-time push."""
        self.running = True
        logger.info("Real-time mail poller loop started.")

        while self.running:
            cfg = load_settings()
            poll_interval = min(max(1, cfg.get("POLL_INTERVAL", 2)), 3)

            try:
                new_otps = await asyncio.to_thread(self._sync_fetch_step)
                # Broadcast status update
                broadcast_event("status", self.get_status_summary())
            except Exception as e:
                logger.error(f"Error in mail loop: {e}")
                self.status = "error"
                self.last_error = str(e)
                broadcast_event("status", self.get_status_summary())

            try:
                await asyncio.wait_for(self.wake_event.wait(), timeout=poll_interval)
                self.wake_event.clear()
            except asyncio.TimeoutError:
                pass

    def stop(self):
        self.running = False
        self.wake_event.set()
        self._disconnect_client()

# Singleton instance
fetcher_service = MailFetcherService()
