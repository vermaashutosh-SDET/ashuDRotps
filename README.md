# ⚡ OTP Share - Live Verification & OTP Mailbox

A lightweight, tempmail-style self-hosted website that automatically fetches OTPs (One-Time Passwords) and verification codes from your personal email (Gmail, Outlook, Yahoo, etc.) and displays them in real-time.

---

## ✨ Features

- **⚡ Tempmail-Style Live Interface**: Beautiful, responsive dashboard inspired by temp-mail services.
- **🔄 Instant Real-Time Push**: Powered by Server-Sent Events (SSE). New OTP emails appear instantly without manual page refreshing.
- **🎯 Smart OTP Detection**: Automatically extracts 4-to-8 digit codes, formatted codes (`123-456`), and verification links from HTML & plain-text emails.
- **📋 1-Click Copy**: Large, prominent OTP display with instant copy to clipboard and visual feedback.
- **🔔 Audio Chime & Notifications**: Built-in pleasant notification sound when an OTP arrives.
- **🏷️ Brand & Service Recognition**: Automatically detects and tags services like Google, Amazon, Netflix, Microsoft, GitHub, Steam, Banks, etc.
- **🔍 Search & Filter**: Instant search across subject, sender, and OTP codes.
- **📖 Full Email Reader**: Inspect the original formatted email, plain text, headers, and click verification links directly.
- **🛡️ Privacy & PIN Protection**: Run locally or set an optional access PIN if exposing it to colleagues or friends over the local network or internet.
- **⚙️ Web-Based Settings & Connection Tester**: Easily test and save your IMAP credentials directly from the browser without restarting.

---

## 🚀 Quick Start (Windows)

### Method 1: One-Click Launch
Double-click `start.bat` in this folder. It will:
1. Check dependencies and install any missing packages.
2. Launch the server at `http://localhost:8000`.
3. Automatically open your browser.

### Method 2: Manual Command Line
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the application
python main.py
```
Then visit **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## 📧 How to Connect Your Gmail (Step-by-Step)

Google requires an **App Password** for third-party IMAP access (you don't use your normal Gmail account password).

1. Open your browser and go to [Google Account Security](https://myaccount.google.com/security).
2. Ensure **2-Step Verification** is turned **ON**.
3. Go directly to **[Google App Passwords](https://myaccount.google.com/apppasswords)**.
4. Enter an app name, for example: `OTP Share`, then click **Create**.
5. Google will display a **16-character code** (e.g. `abcd efgh ijkl mnop`).
6. Open the OTP Share website (`http://localhost:8000`), click **⚙️ Settings**, enter:
   - **Email**: your personal email address (e.g. `yourname@gmail.com`)
   - **App Password**: the 16-character code
   - Click **🔌 Test IMAP Connection** to confirm.
   - Click **💾 Save Settings**!

---

## ⚙️ Configuration Reference (`.env`)

You can edit settings either from the Web UI's **Settings** button or directly in the `.env` file:

| Variable | Default | Description |
|---|---|---|
| `EMAIL_USER` | `""` | Your email address (e.g., `user@gmail.com`) |
| `EMAIL_PASS` | `""` | 16-character IMAP App Password |
| `IMAP_HOST` | `imap.gmail.com` | IMAP server address |
| `IMAP_PORT` | `993` | IMAP SSL port |
| `IMAP_FOLDER` | `INBOX` | Mailbox folder or label to watch |
| `FILTER_KEYWORDS` | `otp,verification,code,...` | Comma-separated keywords to filter for OTP emails |
| `POLL_INTERVAL` | `5` | Check interval in seconds |
| `MARK_AS_READ` | `false` | Set to `true` to mark emails as read when fetched |
| `WEB_PIN` | `""` | Optional access PIN to protect the web feed |
| `PORT` | `8000` | Port for the web server |
| `HOST` | `0.0.0.0` | Bind host (`0.0.0.0` allows LAN devices to access) |

---

## 🧪 Testing

Want to test how the site looks and sounds without waiting for a real email?
Click the **"🧪 Test OTP"** button in the top navigation bar to inject a simulated Google / Netflix / Amazon verification code.

---

## 🔒 Sharing on Local Network or with Colleagues

Because the server binds to `0.0.0.0:8000`, anyone on your Wi-Fi or LAN can access it via your computer's IP:
```
http://<YOUR-PC-IP>:8000
```
To keep your OTPs secure:
- In **Settings**, specify a **Website Access PIN** (e.g. `4921`).
- Anyone accessing the site will be prompted to enter the PIN before any OTPs are displayed.
