import re
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Tuple, Optional, List
from bs4 import BeautifulSoup

KNOWN_SERVICES = [
    ("google", "Google"),
    ("amazon", "Amazon"),
    ("microsoft", "Microsoft"),
    ("apple", "Apple"),
    ("netflix", "Netflix"),
    ("github", "GitHub"),
    ("steam", "Steam"),
    ("uber", "Uber"),
    ("paypal", "PayPal"),
    ("discord", "Discord"),
    ("telegram", "Telegram"),
    ("twitter", "Twitter/X"),
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("meta", "Meta"),
    ("whatsapp", "WhatsApp"),
    ("linkedin", "LinkedIn"),
    ("spotify", "Spotify"),
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("binance", "Binance"),
    ("coinbase", "Coinbase"),
    ("indiabulls", "Indiabulls"),
    ("dhani", "Indiabulls"),
    ("zomato", "Zomato"),
    ("swiggy", "Swiggy"),
    ("flipkart", "Flipkart"),
    ("paytm", "Paytm"),
    ("phonepe", "PhonePe"),
    ("cred", "CRED"),
    ("hdfc", "HDFC Bank"),
    ("icici", "ICICI Bank"),
    ("sbi", "State Bank of India"),
    ("axis", "Axis Bank"),
    ("chase", "Chase Bank"),
    ("wellsfargo", "Wells Fargo"),
    ("bankofamerica", "Bank of America"),
    ("stripe", "Stripe"),
    ("slack", "Slack"),
    ("zoom", "Zoom"),
    ("dropbox", "Dropbox"),
    ("adobe", "Adobe"),
    ("gitlab", "GitLab"),
    ("notion", "Notion"),
    ("reddit", "Reddit"),
    ("tiktok", "TikTok"),
    ("snapchat", "Snapchat"),
]

def decode_mime_header(header_value: Optional[str]) -> str:
    if not header_value:
        return ""
    decoded_fragments = []
    try:
        parts = decode_header(header_value)
        for fragment, encoding in parts:
            if isinstance(fragment, bytes):
                try:
                    decoded_fragments.append(fragment.decode(encoding or "utf-8", errors="replace"))
                except LookupError:
                    decoded_fragments.append(fragment.decode("utf-8", errors="replace"))
            else:
                decoded_fragments.append(str(fragment))
        return "".join(decoded_fragments).strip()
    except Exception:
        return str(header_value).strip()

def detect_service_tag(sender_name: str, sender_email: str, subject: str) -> str:
    combined = f"{sender_name} {sender_email} {subject}".lower()

    for pattern, label in KNOWN_SERVICES:
        if pattern in combined:
            return label

    # Try extracting domain name without TLD
    if "@" in sender_email:
        domain = sender_email.split("@")[-1].lower()
        parts = domain.split(".")
        if len(parts) >= 2:
            brand = parts[-2]
            if len(brand) > 2 and brand not in ("mail", "email", "notification", "noreply", "no-reply"):
                return brand.capitalize()

    if sender_name:
        # Take first 2 words of sender name
        clean_name = re.sub(r"[^\w\s]", "", sender_name).strip()
        words = clean_name.split()
        if words:
            return " ".join(words[:2])

    return "Service"

def extract_otp(subject: str, text_content: str, html_content: str) -> Optional[str]:
    """
    Extracts OTP code using multiple heuristics:
    1. Direct keyword + code proximity in text & subject
    2. HTML emphasized elements (code, strong, font-size)
    3. Isolated digits with contextual cues
    """
    # 1. Check in Subject first if explicit
    subject_patterns = [
        r"(?i)(?:otp|code|verification|passcode)\s*(?:is|:|-|=)?\s*[:#-]?\s*([0-9]{4,8})\b",
        r"(?i)\b([0-9]{4,8})\s*(?:is\s+(?:the|your)?\s*(?:code|otp|one[- ]?time\s+(?:password|code)|verification))\b",
        r"(?i)\b([0-9]{3}[-\s][0-9]{3,4})\b",
    ]
    for pattern in subject_patterns:
        match = re.search(pattern, subject)
        if match:
            code = match.group(1).replace("-", "").replace(" ", "").strip()
            if 4 <= len(code) <= 8:
                return code

    # 2. Check HTML specific tags if available
    if html_content:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            # Look for <code>, or elements with large font / letter-spacing
            candidates = soup.find_all(["code", "strong", "b", "h1", "h2", "span"])
            for el in candidates:
                txt = el.get_text().strip()
                # Check clean 4-8 digit number
                if re.fullmatch(r"[0-9]{4,8}", txt):
                    return txt
                if re.fullmatch(r"[0-9]{3}[-\s][0-9]{3,4}", txt):
                    return txt.replace("-", "").replace(" ", "")
        except Exception:
            pass

    # 3. Check Body Text with High-Priority Patterns
    body_patterns = [
        # "[123456] is the One Time Password (OTP)" / "123456 is your OTP"
        r"(?i)\b([0-9]{4,8})\s+is\s+(?:the|your)?\s*(?:one[- ]?time\s+(?:password|passcode|code)|otp|verification|security\s*code)\b",
        # Explicit verification/OTP code
        r"(?i)(?:verification\s*code|one[- ]?time\s*(?:password|passcode|code)|security\s*code|login\s*code|auth(?:entication)?\s*code|otp\s*(?:code|is)?|passcode|secret\s*code|pin(?:\s*code)?)\s*(?:is|:|-|=)?\s*[:#-]?\s*([0-9]{4,8})\b",
        # Dashed code like 123-456 or 123 456
        r"(?i)(?:code|otp|passcode)\s*(?:is|:)?\s*([0-9]{3}[-\s][0-9]{3,4})\b",
        # "Your code is 123456"
        r"(?i)your\s+(?:temporary\s+)?(?:code|password|passcode|otp)\s+is\s+([0-9]{4,8})\b",
        # "enter 123456" / "use 123456"
        r"(?i)\b(?:enter|use|type)\s+([0-9]{4,8})\b(?:\s+(?:to|for|as|into))?",
        # Alphanumeric codes for services like GitHub (e.g. 6-8 chars with digits and letters)
        r"(?i)(?:verification\s*code|passcode)\s*(?:is|:)?\s*([A-Za-z0-9]{6,8})\b",
        # Standalone lines with only 4-8 digits
        r"(?m)^\s*([0-9]{4,8})\s*$",
    ]

    for pattern in body_patterns:
        match = re.search(pattern, text_content)
        if match:
            code = match.group(1).replace("-", "").replace(" ", "").strip()
            # Avoid matching standard 4-digit years like 2024, 2025, 2026, 2027 if they look like dates
            if len(code) == 4 and code.startswith("20") and int(code) in range(2020, 2035):
                continue
            if 4 <= len(code) <= 8:
                return code

    return None

def extract_verification_link(html_content: str, text_content: str) -> Optional[str]:
    """Finds links like 'Verify Email', 'Confirm Account', 'Click to login'."""
    if html_content:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                txt = a.get_text().strip().lower()
                if not href.startswith("http"):
                    continue
                if any(w in txt for w in ["verify", "confirm", "activate", "log in", "authenticate"]):
                    return href
                if any(w in href.lower() for w in ["verify", "verification", "confirm", "activate-account"]):
                    return href
        except Exception:
            pass

    # Check raw text URLs
    url_match = re.search(r"https?://[^\s<>\"']+(?:verify|confirm|auth|token)[^\s<>\"']*", text_content, re.IGNORECASE)
    if url_match:
        return url_match.group(0)

    return None

def parse_email_message(raw_bytes: bytes, keywords: List[str], sender_filter: Optional[List[str]] = None) -> Optional[dict]:
    """
    Parses a raw email byte stream and returns a dict if it matches filter keywords and sender filter,
    or None if it should be ignored.
    """
    import email
    from email import policy

    try:
        msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    except Exception:
        return None

    # Message-ID
    message_id = msg.get("Message-ID", "")
    if not message_id:
        import hashlib
        # Fallback pseudo-unique hash
        date_header = msg.get("Date", "")
        subj = msg.get("Subject", "")
        message_id = hashlib.sha256(f"{date_header}-{subj}".encode("utf-8", errors="ignore")).hexdigest()

    # Clean Subject
    subject = decode_mime_header(msg.get("Subject", "(No Subject)"))

    # Clean From
    raw_from = msg.get("From", "")
    sender_name, sender_email = parseaddr(raw_from)
    sender_name = decode_mime_header(sender_name)
    if not sender_name and sender_email:
        sender_name = sender_email.split("@")[0]

    # Date
    received_at = None
    date_header = msg.get("Date")
    if date_header:
        try:
            dt = parsedate_to_datetime(date_header)
            received_at = dt.isoformat()
        except Exception:
            pass

    # Extract Text and HTML bodies
    text_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue

            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    text_decoded = payload.decode(charset, errors="replace")
                except LookupError:
                    text_decoded = payload.decode("utf-8", errors="replace")

                if content_type == "text/plain":
                    text_parts.append(text_decoded)
                elif content_type == "text/html":
                    html_parts.append(text_decoded)
            except Exception:
                continue
    else:
        content_type = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    text_decoded = payload.decode(charset, errors="replace")
                except LookupError:
                    text_decoded = payload.decode("utf-8", errors="replace")

                if content_type == "text/html":
                    html_parts.append(text_decoded)
                else:
                    text_parts.append(text_decoded)
        except Exception:
            pass

    body_html = "\n".join(html_parts)
    raw_text = "\n".join(text_parts)

    # If no plain text, convert HTML to plain text
    if not raw_text.strip() and body_html.strip():
        try:
            soup = BeautifulSoup(body_html, "html.parser")
            raw_text = soup.get_text(separator="\n")
        except Exception:
            raw_text = re.sub(r"<[^>]+>", " ", body_html)

    # Check filter keywords: Does subject or text match our OTP keywords?
    searchable_content = f"{subject} {raw_text}".lower()
    matches_filter = any(kw.lower() in searchable_content for kw in keywords)

    # If it doesn't match any filter keywords, skip it!
    if not matches_filter:
        return None

    # Extract OTP code
    otp_code = extract_otp(subject, raw_text, body_html)

    # Detect service / sender tag
    service_tag = detect_service_tag(sender_name, sender_email, subject)

    # Check sender / app filter if configured (e.g. only Indiabulls)
    if sender_filter:
        combined_sender = f"{service_tag} {sender_name} {sender_email} {subject}".lower()
        if not any(target.strip().lower() in combined_sender for target in sender_filter if target.strip()):
            return None

    # Extract verification link if available
    verification_link = extract_verification_link(body_html, raw_text)

    # Snippet (first 160 characters of clean text)
    clean_snippet = re.sub(r"\s+", " ", raw_text).strip()[:160]

    return {
        "message_id": message_id,
        "sender_name": sender_name or "Unknown",
        "sender_email": sender_email or "unknown@domain.com",
        "service_tag": service_tag,
        "subject": subject,
        "otp_code": otp_code,
        "verification_link": verification_link,
        "snippet": clean_snippet,
        "body_text": raw_text,
        "body_html": body_html,
        "received_at": received_at
    }
