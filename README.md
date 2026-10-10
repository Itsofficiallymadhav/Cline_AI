# KaamKaHisab

A WhatsApp assistant (voice or text in, short local-language text out) that helps MNREGA workers check wage delays,
estimate potentially eligible compensation, and prepare a complaint draft for their own review. **Prototype - fictional data - not legal advice.**

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # keys are OPTIONAL; the app works without them
python -m pytest -q                                      # acceptance tests
streamlit run src/channel/simulator_app.py               # chat simulator (no Twilio needed)
uvicorn src.main:app --port 8000                         # webhook for Twilio sandbox
ngrok http 8000                                          # then paste https://<id>.ngrok-free.app/twilio/whatsapp into Twilio
```
Demo job cards: `1001` delayed (Rs 36) - `1002` on time - `1003` unpaid - `1004/1005/1006` need review (missing date / mismatch / failed payment) - `9999` not found.

**Fix the demo date.** Job card `1003` is unpaid, so its delay and amount grow every day
(Rs 36 on 2026-10-10, Rs 51 on 2026-10-20). For a repeatable demo add `AS_OF_DATE=2026-10-10` to `.env`.
`1001` is always Rs 36 (12 days late, both dates fixed).

## Optional keys (`.env`, see `.env.example`)
Everything works with an empty `.env`: regex extraction, template text, typed input, sample data.

| Key(s) | Adds | Without it |
|---|---|---|
| `GEMINI_API_KEY` (+ `GEMINI_MODEL`, default `gemini-3.8-flash`) | better field extraction, friendlier phrasing (always grounding-checked) | regex + templates |
| `GROQ_API_KEY` | voice notes (Whisper `whisper-large-v3`) | "please type" reply |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `PUBLIC_BASE_URL` | WhatsApp sandbox, signature check, voice-note replies | simulator only; signature check skipped |

WhatsApp voice notes need BOTH `GROQ_API_KEY` and the Twilio REST credentials; otherwise the worker gets an immediate "please type" reply.
Set `PUBLIC_BASE_URL` to the exact public https URL (e.g. the ngrok URL) whenever `TWILIO_AUTH_TOKEN` is set, or signatures are not checked (a warning is logged).
None of these keys has been tested live from this repo yet.

## Docs
`SPEC.md` (requirements, contracts, tests, ownership) - `docs/IMPLEMENTATION_GUIDE.md` (who builds what, in what order, Cline prompts) -
`CLINE_LOG.md` (how Cline was used) - `.clinerules` (standing rules).

## Limitations (be upfront in the demo)
Rule values must be verified against official MGNREGA guidance (`rules/delay_rules.json`); sample data only; no government filing;
speech recognition and translations need native-speaker checking; Twilio sandbox is for testing only.
