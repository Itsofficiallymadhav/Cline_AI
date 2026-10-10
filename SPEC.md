# KaamKaHisab - SPEC (source of truth for people and for Cline)

**Pitch:** A WhatsApp assistant that helps MNREGA workers check wage delays, spot possible record discrepancies,
estimate potentially eligible compensation, and prepare a complaint draft in their own language - which the worker reviews and approves.
**User:** a rural worker with a job card, low literacy, sends **voice notes or short text in their own language**; the bot replies in **short text in that language**.
**Not legal advice.** Every result is an illustrative estimate. Real rules must be verified (see section 4).

## 1. Scope
Must: language choice - job card (voice/text) - record lookup - delay detection - deterministic compensation - plain-language explanation -
calculation view - complaint draft (edit) - explicit approval - saved case + STATUS.
Out of scope: filing to any government portal (we only say "hand it to your Gram Panchayat"), live scraping as a dependency, PDFs (optional).

## 2. Architecture
```
Twilio WhatsApp sandbox -> POST /twilio/whatsapp ─┐
Streamlit simulator ──────────────────────────────┴-> channel/flow.handle_message(user_id, text|audio) -> Reply
                      flow uses: ai (extract / explain / complaint / transcribe) | engine (calculator + rules) |
                                 adapters (records) | channel/store (SQLite sessions + cases) | messages (hi/en text)
```
Free stack: FastAPI, SQLite, Gemini free tier (optional), Groq Whisper free tier (optional), Twilio WhatsApp sandbox, ngrok/cloudflared.
The app runs with **no API keys** (templates + regex + sample data). Keys only improve extraction/phrasing/transcription.

## 3. Data contracts (src/engine/models.py)
- `WorkerRecord`: job_card_no, worker_name, village, muster_roll_closed_on, days_worked, daily_wage_rate, days_paid, payment_amount, payment_date, payment_status (success|failed|pending)
- `CalcResult`: status, job_card_no, worker_name, village, wage_amount, payment_amount, closure_date, due_date, payment_date, as_of_date, delay_days, **compensation (None unless delayed/unpaid_overdue)**, rate_per_day, due_days, formula, flags[], evidence[], rule_source, rule_verified, disclaimer
- `Status`: on_time | delayed | unpaid_overdue | needs_review | not_found
- `Flag`: missing_closure_date | missing_wage_data | days_mismatch | wage_rate_mismatch | failed_transaction
- `Reply`: text, options[{id,label}], hint; `render()` appends the numbered list. `ExtractedFields`: job_card, work_period, issue_type. `Case`: case_id, user_id, job_card_no, status, complaint_text, compensation, created_at
- Adapter: `get_records(job_card) -> list[WorkerRecord]` (empty list if unknown). Rules file: `rules/delay_rules.json {due_days, rate_per_day, source, last_verified, note}`.

## 4. Engine rules
- `due_date = muster_roll_closed_on + due_days`; `delay_days = max(0, (payment_date or today) - due_date)`; `compensation = wage_amount x rate_per_day x delay_days` (Decimal, 2 dp, half-up); `wage_amount = days_worked x daily_wage_rate`.
- Any flag => `needs_review`, `compensation = None`. Unpaid & not yet due => `on_time`.
- **VERIFY BEFORE TRUSTING (T1+T4, 15 min):** due_days, rate and the day-counting convention against an official worked example. Then set `last_verified` in the rules file. Until then results carry "Rule values not yet verified."
- Demo example (illustrative): 20 days x Rs 300 = Rs 6,000, paid 12 days late: 6000 x 0.0005 x 12 = **Rs 36**.

## 5. Conversation flow (numbered replies; YES/NO/STATUS/CANCEL words also work)
`hi` -> **language** (1 हिन्दी, 2 English) -> **job card** (voice/text; digits normalised) -> **confirm** read-back (1 yes / 2 no) ->
**result** (explanation; options: calc, draft [only if delayed/unpaid_overdue], cancel) -> **calculation** (dates + formula) ->
**draft** (approve / edit / cancel) -> **approve** (explicit) -> case KH-101 saved, status "ready to hand over", NOT filed -> `status` lists cases.
Failures: unknown job card -> ask again; bad/failed voice -> ask to type; garbage -> re-ask with same options; needs_review -> no amount, no complaint option, "contact Gram Panchayat".

## 6. Acceptance tests (tests/)
`test_calculator.py` (on-time, 1/8/40 days, unpaid, not-yet-due, missing date, days mismatch, rate mismatch, failed txn, demo=36, rules disclosure, no-LLM) -
`test_adapter.py` - `test_ai.py` (extraction incl. Devanagari digits, grounding, LLM mocked) - `test_flow.py` (full journeys en/hi, edit, cancel, voice, isolation) - `test_webhook.py`.
Definition of done: `python -m pytest -q` is green, the simulator completes the journey, and the Twilio sandbox completes it on a real phone.

## 7. Ownership (one owner per file avoids merge conflicts)
| Owner | Files |
|---|---|
| T1 Backend/engine | src/engine/calculator.py, src/adapters/sample.py, data/sample_records.json, rules/delay_rules.json, tests/test_calculator.py, tests/test_adapter.py |
| T2 AI/language | src/ai/*, src/messages.py (translations), tests/test_ai.py |
| T3 Conversation/channels | src/channel/flow.py, store.py, simulator_app.py, twilio_webhook.py, tests/test_flow.py, tests/test_webhook.py |
| T4 Integration/submission | SPEC.md, .clinerules, CLINE_LOG.md, README.md, src/main.py, requirements, repo/CI, demo video, PPT |
Shared (change only by agreement): src/engine/models.py, src/config.py.
