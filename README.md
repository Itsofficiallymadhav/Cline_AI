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

## Docs
`SPEC.md` (requirements, contracts, tests, ownership) - `docs/IMPLEMENTATION_GUIDE.md` (who builds what, in what order, Cline prompts) -
`CLINE_LOG.md` (how Cline was used) - `.clinerules` (standing rules).

## Limitations (be upfront in the demo)
Rule values must be verified against official MGNREGA guidance (`rules/delay_rules.json`); sample data only; no government filing;
speech recognition and translations need native-speaker checking; Twilio sandbox is for testing only.
