# PRICEWAR — Email Confirmation System (Rex Checkout Safety Gate)

> **Complete extraction and reproduction guide for the SMTP-based confirmation email system.**
> 
> This covers **how emails are sent to the user** ("another person" in the autonomous checkout flow), all libraries, DB schema, full code paths, config, image embedding logic, confirmation token flow, and exact steps to reproduce **without errors** in another project.
> 
> Read alongside `files/05_PROJECT_ARCHITECTURE.md` and `backend/agents/rex.py`.

---

## 1. Overview

The **only email sending** in the project occurs in the Rex autonomous checkout (`run_voice_checkout`). It sends a rich HTML confirmation email **before** Rex performs browser-based checkout with the user's saved payment profile.

- **Purpose**: "Pay-on-proof" / safety gate. User must click "Confirm order" link in email (validates token, unblocks agent).
- **Recipient**: `CONFIRM_EMAIL` (from `.env`) **or** `payment_profiles.email`.
- **No other emails**: No outbound to businesses, no marketing, no Clerk transactional emails (Clerk is only for auth in frontend).
- **Frontend role**: War Room dashboard shows `AWAITING_CONFIRMATION` status (📧 emoji), Gmail screenshot verification for post-purchase proof (`UnifiedRexPanel.jsx`).

**Key innovation**: Product image is **automatically fetched and inlined as data:URI** (bypasses "load images" in Gmail). Uses pure stdlib (no SendGrid/Resend).

---

## 2. Tech Stack Specific to Email

### Backend Libraries (from `backend/requirements.txt`)
| Package | Version | Role in Email Path |
|---------|---------|--------------------|
| `fastapi` | `0.115.12` | Routes (`/rex/checkout/{id}/confirm`), `BackgroundTasks`, WS broadcasts |
| `pydantic-settings` | `2.9.1` | Typed `.env` loading (`Settings` class) |
| `aiosqlite` | `0.21.0` | Persist `confirm_token` + status in `checkout_orders` |
| `Pillow` | `>=10` | (Indirect — screenshots elsewhere) |

**Stdlib only for core SMTP** (no extra deps):
- `smtplib`, `email.mime.*` (multipart/alternative)
- `urllib.request` (page scrape + image download with Chrome UA)
- `base64`, `html`, `re`, `secrets`, `concurrent.futures`, `asyncio`, `logging`

**No** external email SDKs. See `backend/services/email_sender.py:1`.

**Config**: `backend/config.py:41-47` + `.env`.

---

## 3. Configuration (`.env` + `config.py`)

```env
# === EMAIL (SMTP) — for checkout confirmation emails ===
# Use a Gmail account with an App Password (not your regular password)
# Generate one at: https://myaccount.google.com/apppasswords
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=yourgmail@gmail.com
SMTP_PASS=xxxxxxxxxxxxxxxx  # 16-char App Password
CONFIRM_EMAIL=yourinbox@example.com
CHECKOUT_BASE_URL=http://localhost:8000  # Must be reachable from email client
```

From `backend/config.py`:

```python
# backend/config.py:41
# ── Email / SMTP ───────────────────────────────────────────────
SMTP_HOST: str = "smtp.gmail.com"
SMTP_PORT: int = 587
SMTP_USER: str = ""        # Gmail address used to SEND confirmation emails
SMTP_PASS: str = ""        # Gmail App Password (not account password)
CONFIRM_EMAIL: str = ""    # Where confirmation emails are SENT TO (your personal inbox)
CHECKOUT_BASE_URL: str = "http://localhost:8000"  # Public base URL for confirm links
```

Loaded fresh in `main.py:92` (lifespan).

**Payment profile** (`POST /rex/payment-profile`) supplies fallback email + card details.

---

## 4. Database Schema (`backend/db/database.py`)

```sql
-- checkout_orders (core table)
CREATE TABLE IF NOT EXISTS checkout_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    intent          TEXT NOT NULL,
    product_name    TEXT,
    retailer        TEXT,
    negotiated_price REAL,
    savings         REAL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'SEARCHING',  -- AWAITING_CONFIRMATION key state
    confirm_token   TEXT,           -- secrets.token_urlsafe(32)
    confirmed_at    TEXT,
    ...
);

-- payment_profiles (email source)
CREATE TABLE IF NOT EXISTS payment_profiles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL,
    cardholder_name TEXT NOT NULL,
    ...
);
```

**Auto-migration** (lines 126-135 in `database.py`) adds `confirm_token`/`confirmed_at` columns on startup. Called in `main.py` lifespan.

Models in `backend/db/models.py:164` (`PaymentProfile`, `RexCheckoutRequest`, `CheckoutUpdateEvent` for WS).

---

## 5. Complete Flow

1. **Trigger** — `POST /rex/checkout` (`payment_routes.py:126`) → creates order row → backgrounds `run_voice_checkout(order_id, ...)`.

2. **Step 3: Email** (`rex.py:~3301`):
   - Generate token, persist to DB.
   - Register `asyncio.Event` in global `_confirm_events[order_id]`.
   - Build confirm URL.
   - **Run email send in ThreadPool** (SMTP is sync):
     ```python
     # rex.py:3332
     from services.email_sender import send_checkout_confirmation_email
     # ... ThreadPoolExecutor + run_in_executor ...
     email_ok = await loop.run_in_executor(pool, _send)
     ```
   - Broadcast WS (`rex_checkout_update` with `AWAITING_CONFIRMATION` + 📧).
   - `await asyncio.wait_for(confirm_event.wait(), timeout=30*60)`.

3. **Email Generation** (`email_sender.py:105`):
   - Fetches product page → extracts `og:image` via regex → downloads → `data:image/...;base64,...` URI.
   - Builds **table-based HTML** (Gmail-friendly, inline styles, yellow Amazon-style CTA).
   - Multipart (HTML + plaintext fallback).
   - `smtplib.SMTP` with STARTTLS + login (Gmail-specific error handling).

4. **User Clicks Link** — `GET /rex/checkout/{order_id}/confirm?token=xxx` (`payment_routes.py:208`):
   - Validates token + status.
   - Updates DB (`confirmed_at`, clear token).
   - WS broadcast + `fire_confirm_event(order_id)` → `event.set()`.
   - Returns success HTML (auto-redirect to War Room).

5. **Unblocks** → Rex proceeds to browser checkout (`browser_use.Agent` with payment profile).

**Event helper** (`rex.py:28`):

```python
# backend/agents/rex.py:25
_confirm_events: dict[int, asyncio.Event] = {}

def fire_confirm_event(order_id: int) -> bool:
    event = _confirm_events.get(order_id)
    if event:
        event.set()
        return True
    return False
```

Imported in `payment_routes.py:10`.

---

## 6. Key File: `backend/services/email_sender.py`

**Full critical sections** (copy verbatim):

```1:38:backend/services/email_sender.py
"""SMTP email helper for checkout confirmation emails."""
from __future__ import annotations

import base64
import html as html_module
import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("email_sender")

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
```

The helper functions `_fetch_page_html`, `_extract_candidate_image_urls`, `_download_as_data_uri`, `_resolve_product_image_data_uri` (lines 21-102) are **essential** for reliable inline images.

Main function (lines 105-328) contains the full HTML template (lines 162-281), plaintext, and SMTP block with specific `SMTPAuthenticationError` handling.

**Do not modify the HTML** — it's tuned for email clients.

---

## 7. Reproduction Checklist (Copy-Paste to New Project)

1. **Create project structure**:
   ```
   your-project/
   ├── backend/
   │   ├── services/email_sender.py     # copy entire file
   │   ├── config.py                    # include SMTP section + Settings class
   │   ├── db/database.py               # include checkout_orders + migration
   │   ├── db/models.py                 # PaymentProfile, CheckoutUpdateEvent
   │   ├── routes/payment_routes.py     # confirm endpoint + init func
   │   ├── agents/rex.py                # _confirm_events, fire_confirm_event, Step 3 in run_voice_checkout
   │   ├── main.py                      # lifespan init, router mount under /rex
   │   └── requirements.txt             # add the listed packages
   ```

2. **Install**: `pip install -r requirements.txt`

3. **.env**: Copy SMTP section (use real Gmail App Password).

4. **Init**: Call `init_db()`, `init_payment_routes(...)` in lifespan.

5. **Run**: `uvicorn backend.main:app --reload`

6. **Test**:
   - Save payment profile (includes email).
   - POST to `/rex/checkout` with intent.
   - Check Gmail for email (with embedded image).
   - Click confirm link → should unblock, update UI via WS.

**Exact code to integrate** is in the files listed above. Match the WS event shapes exactly for dashboard compatibility.

---

## 8. Common Pitfalls & Error Fixes

- **Authentication fails**: "Gmail authentication failed — check SMTP_USER and SMTP_PASS (must be an App Password...)". See error in `email_sender.py:322`.
- **No images**: Network/UA issues — helpers have generous timeouts and fallbacks.
- **Blocking event loop**: **Always** use `ThreadPoolExecutor` for `send_checkout_confirmation_email`.
- **Token expired/invalid**: 30min timeout + one-time use (token cleared on confirm).
- **DB columns missing**: Migration runs automatically on first startup.
- **Link not clickable**: Ensure `CHECKOUT_BASE_URL` is public/correct (CORS is `*`).
- **Email blocked by spam filters**: Use consistent From address + good HTML (current template passes Gmail).
- **Concurrent events**: Global dict cleaned in `finally` block.
- **Frontend**: Update War Room to handle `AWAITING_CONFIRMATION` and `rex_order_confirmed` WS events (see `UnifiedRexPanel.jsx:~898`).

**Production notes**: Add rate limiting, proper domain/DKIM, HTTPS, monitoring on SMTP errors. Current setup is dev-oriented (localhost redirect).

---

## 9. Related Frontend References

- `warroom/src/components/rex/UnifiedRexPanel.jsx`: Gmail screenshot verification, `AWAITING_CONFIRMATION` UI, payment profile email field.
- `warroom/src/context/PriceWarContext.jsx`: `verifyScreenshot`, paymentProfile.email.
- WS hook in `useWebSocket.js`.

See also `files/03_REX_AGENT.md` and `files/04_WAR_ROOM_DASHBOARD.md` for full Rex context.

---

**This document contains everything needed to reproduce the email system error-free.** The combination of token-based confirmation, inline data URIs, async event waiting, and Gmail SMTP is fully self-contained in the cited files.

Last updated: 2026-04-19
```

**File created successfully at `files/06_EMAIL_CONFIRMATION_SYSTEM.md`.**

You can open it now in the editor. It follows the exact style and depth of the other `files/*.md` documents (e.g. `05_PROJECT_ARCHITECTURE.md`). Let me know if you want adjustments, more code excerpts, or a standalone minimal reproduction repo setup.