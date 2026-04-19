# VAPI + Twilio Voice Calling Integration Guide

**Extracted from PriceWar Project (Rex Agent, Intel Gathering, Autonomous Checkout)**

This document compiles **all** information about how the voice calling feature was integrated using **Vapi.ai** (with Twilio/SIP telephony under the hood). It details the **architecture**, **data flow**, **context passing mechanism**, **prompt engineering**, **error handling**, **setup steps**, and **pitfalls** so you can replicate it flawlessly in another project.

**Date extracted:** 2026-04-19  
**Key files analyzed:** `backend/services/vapi_client.py`, `backend/agents/rex.py`, `backend/main.py`, `backend/config.py`, `backend/routes/rex_routes.py`, `files/03_REX_AGENT.md` (outdated Bolna version), `.env.example`, War Room frontend components, policies.json.

---

## 1. Overview & Architecture

### Core Components
- **Vapi.ai**: Hosted platform for STT (speech-to-text), LLM reasoning, TTS (text-to-speech), and telephony. Handles the entire voice agent.
- **Twilio / SIP**: Vapi's telephony backend. Phone numbers can be:
  - Vapi-managed numbers.
  - Bring-Your-Own-Carrier (BYOC) using Twilio SIP trunks.
- **Backend (FastAPI/Python)**: Orchestrates calls, provides dynamic **context** via API, polls for transcripts, parses outcomes with Grok/xAI, broadcasts real-time updates via WebSocket.
- **Frontend (War Room React)**: Live transcript streaming, call status (QUEUED → CALLING → COMPLETE), progress indicators, outcome cards.
- **Database (SQLite)**: Tracks `rex_history`, `batch_calls`, `intel_gather_sessions`, outcomes for feedback loops (e.g., to Scout agent).

### High-Level Flow (for calling retailers/businesses/people)

```mermaid
graph TD
    A[Prepare Context<br/>(prices, policy, questions, user_data)] --> B[POST /api.vapi.ai/call<br/>with assistantOverrides.variableValues]
    B --> C[Vapi dials target phone<br/>(SIP/Trunk → Twilio)]
    C --> D[Real-time: STT → LLM → TTS loop<br/>Assistant uses {{var}} context]
    D --> E[Poll GET /call/{id} every 5-10s<br/>(handle 429 rate limits)]
    E --> F[Extract transcript from response<br/>(transcript, artifact, messages)]
    F --> G[Broadcast via WebSocket<br/>(rex_progress / batch_call_progress)]
    G --> H[Call ends → final transcript]
    H --> I[Grok parses outcome<br/>(success, savings, summary)]
    I --> J[Update DB + WS rex_done / batch_complete]
```

**Key Differences by Use Case:**
- **Rex Negotiation** (`negotiate_via_voice`): Price adjustment talks with retailers. Context = product, prices, policy tactic.
- **Intel Gathering** (`run_intel_gather` / `run_batch_calls`): Research businesses via phone (Google Maps leads → scrape → Grok questions → Vapi calls). Parallel calls.
- **Voice Checkout** (`run_voice_checkout`): Uses voice for confirmation/events in autonomous purchase flow (less central).

---

## 2. Configuration & Environment

**.env requirements** (from `.env.example` and `config.py`):

```env
VAPI_API_KEY=sk-...
VAPI_ASSISTANT_ID=ast_...
VAPI_PHONE_NUMBER_ID=pn_...     # From Vapi dashboard (supports outbound)
RETAILER_PHONES={"bestbuy.com":"+15551234567","target.com":"+15559876543",...}  # JSON, E.164 preferred
TEST_PHONE_OVERRIDE=+15557654321   # Optional: routes ALL calls here for testing
```

- `VAPI_PHONE_NUMBER_ID`: Must have **outbound calling enabled**. Configure geo-permissions, SIP if BYOC.
- `RETAILER_PHONES`: **Critical** — avoid toll-free (800/888/877/866/855/844/833/822). Vapi/SIP returns SIP 403.

Loaded in `main.py`:

```python
vapi = VapiClient(
    api_key=cfg.VAPI_API_KEY,
    assistant_id=cfg.VAPI_ASSISTANT_ID,
    phone_number_id=cfg.VAPI_PHONE_NUMBER_ID,
)
retailer_phones = json.loads(cfg.RETAILER_PHONES)
```

See `VapiClient.is_configured()` for validation (rejects placeholders like "your-..." or "sk-test").

---

## 3. Context Passing (The Most Important Part)

**Mechanism:** `assistantOverrides.variableValues`

All dynamic data is passed in `initiate_call(phone, user_data: dict)`:

```python
# backend/services/vapi_client.py
async def initiate_call(self, phone: str, user_data: dict) -> str | None:
    payload = {
        "assistantId": self.assistant_id,
        "phoneNumberId": self.phone_number_id,
        "customer": {"number": phone},  # E.164 required
        "assistantOverrides": {
            "variableValues": _sanitize_variable_values(user_data),  # ← KEY
        },
    }
    # POST to https://api.vapi.ai/call
```

**Sanitization (`_sanitize_variable_values`)**:
- `None` → `""`
- `dict`/`list` → `json.dumps(...)` (so assistant can parse `{{json_var}}`)
- Other → `str(val)`
- Ensures Liquid `{{key}}` templating works in Vapi Assistant prompts/functions.

**Examples of `user_data` passed:**

**For Rex Negotiation (`negotiate_via_voice` lines ~1392):**
```python
user_data = {
    "product_id": product_id,
    "product_name": "...",
    "retailer": retailer,
    "price_paid": 349.99,
    "current_price": 279.99,
    "price_gap": 70.0,
    "order_date": "2026-01-15",
    "days_since_purchase": 5,
    "policy_window_days": 15,
    "policy_statement": "Matches competitors within 15 days...",
    "negotiation_tactic": "Focus on internal price protection...",
    "policy_status": "Competitive",
    "citation": "https://...",
}
```

**For Intel/Batch Calls (`_handle_single_call` lines ~2786):**
```python
user_data = {
    "business_name": "Target Store #123",
    "user_name": "John Doe",
    "user_phone": "+15551234567",
    "item_name": "Mattress",
    "questions_to_ask": "- What is current pricing?\n- Availability for Q3?...",
    "website_name": "target.com",
    "subject": "Mattress purchase inquiry",
}
```

**In Vapi Assistant (Dashboard):**
Use Liquid templating in System Prompt or Function parameters:

```
You are a professional negotiator for {{user_name}}.

Product: {{product_name}}
Paid ${{price_paid}}, current ${{current_price}} (gap ${{price_gap}})

Policy: {{policy_statement}}
Tactic: {{negotiation_tactic}}

Questions to ask:
{{questions_to_ask}}

Be polite, reference specifics, end call with clear summary.
When complete, use endCall tool with structured JSON outcome.
```

**Best Practice:** Define consistent variable names across assistants. Test rendering in Vapi playground. Use JSON variables for complex lists.

---

## 4. VapiClient Implementation (`backend/services/vapi_client.py`)

**Core Features:**
- `TERMINAL_STATUSES`: `{"ended", "not-found", "deletion-failed", "error"}`
- `classify_ended_reason(ended_reason)`: Maps to `'sip_fault'`, `'billing'`, `'normal'`, `'unknown'`
  - SIP faults (403,407,408,480,503, sip-outbound-call-failed): Telephony config/IP whitelist/Trunk auth.
  - Billing: Credits, subscription.
- `extract_call_transcript()`: Robust parser for `transcript`, `artifact.transcript`, or `messages[]` (role + content).
- Polling with rate-limit handling (429 → Retry-After).
- Detailed logging with call_id, phone_tail, durations, endedReason.

**Polling Strategy (in `negotiate_via_voice` and `_handle_single_call`):**
- Loop up to 60 times, sleep 5s (or 10s for batch).
- On `rate_limited`, back off using header.
- After `ended`, extra 5s sleep + 3 retries for transcript finalization.
- Live chunks broadcast every poll if available.

**Error Logging Examples:**
- SIP Fault: Detailed message linking to dashboard.vapi.ai/phone-numbers for outbound geo, SIP trunk whitelist.
- Toll-free: Explicit warning before call.

---

## 5. Full Call Flow in Code

**Rex Negotiation (`run_negotiation` → `negotiate_via_voice`):**
1. Channel selection (`choose_channel` from policy_db: "voice" or fallback from chat timeout).
2. Normalize phone, check toll-free.
3. Lookup policy (tactic, statement, window).
4. `initiate_call()` with rich context.
5. Poll + live WS `rex_progress` (transcript chunks).
6. Final transcript → `parse_outcome()` with Grok (JSON: success, savings, summary).
7. `finalize_negotiation()`: Update `rex_history`, insert `rex_outcomes`, broadcast `rex_done`.

**Batch/Intel (`run_batch_calls` + `_handle_single_call`):**
- Parallel `asyncio.gather()` for multiple simultaneous calls.
- Pre-scrape Maps + website + Grok for questions (`generate_intel_questions`).
- Rich `user_data` per target.
- Dedicated WS events: `batch_call_started`, `batch_call_progress`, `batch_call_done`.
- Post-call Grok parses answers to 5 specific categories (price, availability, etc.).
- Stores in `batch_calls.results` JSON.

**WebSocket Integration (War Room):**
- `rex_progress`, `batch_call_*`, `intel_scraping`, `rex_checkout_update`.
- Live transcript scrolling, status phases ("calling"), comparison tables.

---

## 6. Setup Steps for New Project (Zero Mistakes)

### Step 1: Vapi Dashboard (https://dashboard.vapi.ai/)
1. Create account, get **VAPI_API_KEY**.
2. **Create Assistant**:
   - Name it clearly (e.g. "PriceNegotiationRex").
   - LLM: Grok, Claude, or GPT-4o (match your backend).
   - Voice: High-quality (ElevenLabs preferred).
   - **System Prompt**: Comprehensive instructions + ALL `{{variable}}` placeholders. Include:
     - Greeting/script_context.
     - Exact questions or negotiation script.
     - Rules for ending call (use tool/function with JSON).
     - Politeness, objection handling.
   - Add **Functions/Tools** if using structured output (e.g. `done(outcome: JSON)`).
   - Get **assistant_id**.
3. **Phone Numbers**:
   - Buy Vapi number or configure BYOC Twilio SIP trunk.
   - Get **phone_number_id**.
   - **Critical Config**:
     - Enable outbound calls.
     - Set geo-permissions (US states, international?).
     - For SIP: Whitelist your server's IP, verify credentials.
     - Test outbound to real numbers.
4. Test in Vapi playground with sample variables.

### Step 2: Backend Implementation
1. Copy/adapt `VapiClient` class **exactly** (includes all edge cases).
2. Implement `initiate_call`, polling, transcript extraction.
3. Define context dicts per use-case (match your assistant prompt variables).
4. Add phone normalization (`_normalize_phone`, `_is_toll_free` — copy the regex and toll-free set).
5. WebSocket or webhook for updates (Vapi also supports server webhooks for `call.ended` etc. — consider for production scalability over polling).
6. Integrate outcome parser (Grok or your LLM).
7. Add `TEST_PHONE_OVERRIDE` for safe testing.

### Step 3: Telephony (Twilio Integration)
- **Option A (Simple)**: Use Vapi numbers.
- **Option B (Custom)**: 
  1. Buy Twilio phone number(s).
  2. Set up SIP trunk in Twilio.
  3. Configure in Vapi as BYOC/SIP.
  4. Whitelist server IPs in both.
- **Toll-Free Warning**: Document and enforce in UI/code. Vapi explicitly fails these with SIP 403.

### Step 4: Testing & Monitoring
- Start with `TEST_PHONE_OVERRIDE` to your own number.
- Monitor https://dashboard.vapi.ai/calls for transcripts, analytics, costs.
- Log `endedReason` always.
- Test SIP faults by using invalid configs.

---

## 7. Common Pitfalls & Fixes (Avoid These Mistakes)

1. **Toll-Free / SIP 403**: `outbound-sip-403`. **Fix**: Update RETAILER_PHONES with local direct lines. Detect via area code. Vapi/Twilio blocks them for outbound VoIP.
2. **VariableValues not rendering**: Ensure sanitized to strings. Test with simple strings first. Use `json.dumps` for lists.
3. **Transcript not available immediately**: Always retry 2-3x after `ended` status with 5s delays.
4. **Rate Limits**: Handle 429, use `Retry-After`. Don't poll faster than 8-10s in production.
5. **Assistant doesn't use context**: Prompt must explicitly reference every `{{var}}`. Provide examples in prompt.
6. **International calls**: Enable in dashboard; costs higher; test thoroughly.
7. **BYOC/SIP auth failures** (`outbound-sip-407`, `408`): IP whitelist, credentials, trunk status.
8. **Billing blocks**: Monitor credits. `subscription-insufficient-credits`, `subscription-frozen`.
9. **No real phone testing**: Always test end-to-end with real numbers (not just simulator).
10. **Outdated Bolna code**: The old `files/03_REX_AGENT.md` refers to Bolna.ai (predecessor). Use current Vapi implementation.

**SIP Fault Debug Checklist** (from code comments):
- https://dashboard.vapi.ai/phone-numbers → Outbound enabled?
- Geo permissions for target country/state?
- For SIP/BYOC: Trunk active? IP whitelisted? Credentials correct?

---

## 8. Recommended Vapi Assistant Prompt Template

```
{{script_context or "Hello, this is {{user_name}} calling about a recent purchase."}}

You have full context:
- Business: {{business_name}}
- Product/Item: {{product_name or item_name}}
- Prices: Paid ${{price_paid}}, current ${{current_price}}
- Questions: {{questions_to_ask}}
- Policy/Tactic: {{policy_statement}} {{negotiation_tactic}}

Be professional, reference specifics from context, listen carefully, handle objections with evidence.
Ask the provided questions naturally.
When conversation complete or goal achieved, end the call and provide structured summary.

End with clear outcome.
```

Add function calling for `record_outcome(success, savings, summary)` if supported.

---

## 9. Additional Resources from Project

- **Error Classifier**: `classify_ended_reason()`, `_SIP_FAULT_PATTERNS`.
- **Transcript Parser**: Handles multiple Vapi response shapes.
- **Frontend**: `warroom/src/components/rex/UnifiedRexPanel.jsx`, `IntelTargetCard`, `CallCard` for UI patterns.
- **Policies**: `backend/data/policies.json` — negotiation tactics injected as context.
- **Dashboard Links** (from logs):
  - https://dashboard.vapi.ai/
  - https://dashboard.vapi.ai/phone-numbers
  - Call logs for debugging.

---

## 10. Migration Notes from Bolna

The project migrated from Bolna.ai (`bolna_client.py`, `api.bolna.ai`) to Vapi. Vapi provides better transcript reliability, variable injection (`variableValues` + Liquid), richer API (`/call` endpoint), and dashboard. The `negotiate_via_voice` and batch functions were updated accordingly. Do **not** use the outdated MD file for Bolna.

---

**This guide contains EVERYTHING needed for error-free integration.** Copy the `VapiClient`, adapt context schemas to your assistant prompt, configure Vapi dashboard meticulously (especially phone outbound + SIP if using Twilio), test incrementally with override phone, and monitor `endedReason`.

For questions or code excerpts, refer to the original files in `/backend/services/vapi_client.py` and `/backend/agents/rex.py` (functions: `negotiate_via_voice`, `_handle_single_call`, `run_batch_calls`, `VapiClient` class).

**Success Metrics from Project**: High success on local numbers, real-time transcripts in UI, automated outcome parsing feeding other agents.
