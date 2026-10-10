# KaamKaHisab - Implementation Guide (who builds what, in what order, with Cline)

The repo you have is **Task 1 (scaffold) already done**: folder structure, shared contracts (`src/engine/models.py`),
rules file, sample data, Hindi/English messages, `SPEC.md`, `.clinerules`, and **42 acceptance tests, 39 of which fail
until you implement the stubs**. Your job is to make them pass - with Cline - one module per person, in parallel.

Check where you stand any time: `python -m pytest -q` (green = done).

---
## 0. Setup (everyone, first 15 minutes)
1. Install Python 3.10+ and VS Code. In VS Code install the **Cline** extension; add your API key/model in its settings (each person on their own laptop).
2. Optional CLI: `npm i -g cline` then authenticate per the current Cline docs (docs.cline.bot - read the CLI/SDK page first, interfaces change).
3. T4 creates the **public GitHub repo** and pushes this folder to `main`. Everyone clones it.
4. `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cp .env.example .env && python -m pytest -q`
   (you should see "39 failed, 3 passed" - that is the starting line).
5. Each person works on their own branch: `git checkout -b t1-engine` (t2-ai, t3-channel, t4-integration). **Edit only the files you own** (SPEC.md section 7).

## 1. Cline memory (already in the repo - read before your first prompt)
- `SPEC.md` - requirements, contracts, flow, tests, ownership. Start every Cline task with "Read SPEC.md and .clinerules".
- `.clinerules` - standing rules (no auto-submit, no LLM in the engine, grounded text only, synthetic data, small steps).
- `CLINE_LOG.md` - **fill one row after every accepted Cline task**. This is your evidence for the video, README and PPT.

## 2. Working method with Cline (all four)
1. **Plan Mode first.** One task, read its plan, correct it ("use Decimal", "don't touch models.py") before it writes code.
2. **Act Mode in small steps**, one function/module at a time, tests after each.
3. **Review every diff; run `python -m pytest -q <your test file>` yourself.**
4. **Commit after each green step** (`git commit -m "T1: calculator passes 14 tests"`). Use Cline checkpoints to compare/restore.
5. **Fresh Cline task per module** so context stays clean.
6. **Auto-approve carefully:** reading/editing files is fine; keep manual approval for commands that delete files or use the network.
7. **Screen-record** the first Plan Mode session, one red-to-green test run, and any Cline-in-product moment.
8. Never weaken a test to pass it. If a test looks wrong, tell the team and change SPEC.md + the test together.

## 3. Parallel plan - who builds what

### Dependency picture (why you can all start at minute 0)
```
T1 engine+adapter ──┐
T2 ai (extract, explain, complaint, transcribe) ──┼──> T3 flow uses both (needs their FIRST versions)
T3 store, simulator, webhook helpers (independent) ┘
T4 repo, SPEC, CI, Twilio account, README, video/PPT prep (independent), integration from hour 1.5
```
**Rule:** T1 and T2 push a *first, simple, passing version within ~45 minutes* (calculator happy path; template explanations; regex extraction).
Improve afterwards. T3 starts with the parts that need nobody (store, simulator UI, webhook helpers), then the flow once T1/T2 land.

### T1 - Backend / engine (owner of the numbers)
Files: `src/engine/calculator.py`, `src/adapters/sample.py` (+ `data/`, `rules/`). Tests: `test_calculator.py`, `test_adapter.py`.
1. **(0:00-0:30) Adapter first** - tiny and unblocks everyone. Cline prompt:
   > Read SPEC.md and .clinerules. In Plan Mode, plan then implement src/adapters/sample.py (SampleAdapter loading data/sample_records.json into WorkerRecord, get_records returns [] for unknown). Do not change models.py. Run tests/test_adapter.py.
2. **(0:30-1:30) Calculator** - Cline prompt:
   > Implement src/engine/calculator.py per its module docstring and SPEC.md section 4, using rules from src/engine/rules.py. delay_days = max(0, (payment_date or today) - (closure_date + due_days)). Uncertain data returns status needs_review and compensation None with flags: missing_closure_date, missing_wage_data, days_mismatch, wage_rate_mismatch, failed_transaction. Use Decimal. Fill evidence and formula. No LLM or network. Run tests/test_calculator.py and fix until green.
3. **(1:30-2:30) Verify the rule** with T4: find the official statement of the payment deadline, compensation rate and day counting; check one official worked example gives the same number; then set `last_verified` + `source` in `rules/delay_rules.json`. **Do not trust the numbers until this is done.**
4. **(2:30-4:30)** edge cases (negative amounts, payment before closure, multiple wage periods per job card), more sample workers if useful, help T3/T4 debug.
**Done when:** `pytest tests/test_calculator.py tests/test_adapter.py` is green and the rules file is verified (or clearly labelled unverified in the demo).

### T2 - AI / language (owner of words and voice)
Files: `src/ai/extract.py`, `explain.py`, `complaint.py`, `transcribe.py` (+ `llm.py`, `utils.py` if needed), translations in `src/messages.py`. Test: `test_ai.py`.
1. **(0:00-0:45) No-key versions first.** Cline prompt:
   > Read SPEC.md and .clinerules. Implement src/ai/extract.py (regex job-card extraction with Unicode digit normalisation and issue_type), explain.py (template_explain, is_grounded, explain with optional LLM rewrite that is used only if grounded) and complaint.py (template). Mock the LLM in tests. Make tests/test_ai.py pass without any API key.
2. **(0:45-2:00) Voice.** Get a free Groq key; implement `transcribe()` (OGG/Opus bytes in, text or None out, never raise). Record two real Hindi voice notes on your phone and test them. Measure how often *numbers* come out wrong.
3. **(2:00-3:30) Language quality.** Get 1-2 native speakers (or a teacher/relative) to review the Hindi in `src/messages.py`; add one more language if time allows (copy the `hi` dict; add the code to `config.SUPPORTED_LANGS` and `LANG_OPTIONS`). Keep sentences short; one idea per message.
4. **(3:30-4:30) LLM polish + safety:** turn on the Gemini key, check the rewrite never adds numbers (the grounding check should reject it), test spoken numbers ("एक शून्य शून्य एक") in `extract_fields`.
**Done when:** `pytest tests/test_ai.py` green with no keys; with keys, a real Hindi voice note produces the right job card, or a clean "please type" fallback.

### T3 - Conversation + channels (owner of the user experience)
Files: `src/channel/store.py`, `flow.py`, `simulator_app.py`, `twilio_webhook.py`. Tests: `test_flow.py`, `test_webhook.py`.
1. **(0:00-0:45) Store + webhook helpers (no dependencies).** Cline prompt:
   > Read SPEC.md and .clinerules. Implement src/channel/store.py (SQLite sessions and cases; read config.DB_PATH at call time) and the helper functions compute_signature, split_text, twiml in src/channel/twilio_webhook.py. Make the matching tests pass.
2. **(0:45-2:30) Flow** (as soon as T1's adapter+calculator and T2's template explain land - `git pull` often). Cline prompt:
   > Implement handle_message in src/channel/flow.py as a state machine: language -> job card -> confirm -> result -> calculation/complaint -> explicit YES approval -> case saved -> STATUS. Numbered replies, store state per user in SQLite, no provider code. Follow the module docstring. Write extra tests for any bug you find. Run tests/test_flow.py.
3. **(2:30-3:15) Simulator** - Streamlit chat page calling `handle_message` (module docstring has the spec). Use it for every demo/test run.
4. **(3:15-4:15) Twilio route** - `POST /twilio/whatsapp` (text -> TwiML reply; audio -> background download + REST reply). Test with the tunnel running and a real phone.
**Done when:** `pytest tests/test_flow.py tests/test_webhook.py` green; the simulator completes the full journey; a real phone completes it through the Twilio sandbox.

### T4 - Integration, quality, submission (owner of "it works and we can prove it")
Files: `SPEC.md`, `.clinerules`, `CLINE_LOG.md`, `README.md`, `src/main.py`, repo setup, video, PPT.
1. **(0:00-0:30)** create the public repo, push scaffold, protect `main` lightly (PRs optional), share the Cline setup steps, make everyone run the baseline tests.
2. **(0:00-1:00) Twilio setup (riskiest external step):** create a Twilio account, enable the WhatsApp sandbox, have each tester send `join <code>`, start `ngrok http 8000`, and confirm Twilio can reach `GET /health` through the tunnel. Fill `.env`.
3. **(1:00 onward) Continuous integration:** every 30 minutes merge green branches into `main`, run the **whole** suite, and report failures to the owner. Keep a short GitHub Actions workflow running `pytest` (optional but nice evidence).
4. **(2:30-3:30) Rule verification with T1;** record the source and date in `rules/delay_rules.json`.
5. **(3:30-4:30) End-to-end test pass** on real WhatsApp: delayed (1001), on time (1002), unpaid (1003), needs review (1004/1005/1006), not found (9999), voice note in Hindi, garbage input, cancel mid-way, edit complaint, STATUS. Log bugs as GitHub issues for owners.
6. **(4:30-5:15)** README final, demo script rehearsed, CLINE_LOG complete, screenshots, a **simulator-based backup demo** recorded in case WhatsApp fails.
7. **(5:15-6:00)** video (60-90 s) + PPT (7 slides, see the plan doc) + fresh-clone test on a different laptop.
**Done when:** a stranger can clone the repo, follow the README, and run the demo.

## 4. Timeline & checkpoints
| Time | Checkpoint |
|---|---|
| 0:00-0:30 | Everyone has the repo, baseline tests run (39 red), branches created, Cline set up, Twilio account started |
| 0:45 | T1 adapter + T2 template/regex versions pushed |
| 1:30 | T1 calculator green; T3 store + webhook helpers green |
| **3:00** | **Hard deadline: full journey works in the simulator with a correct, explainable result** |
| 3:30 | Same journey on real WhatsApp (Twilio sandbox) |
| 4:30 | Feature freeze: only bug fixes. WhatsApp go/no-go - if flaky, demo with the simulator |
| 5:15 | Start recording |

## 5. Demo script (60-90 s) using the sample data
1. Problem (10 s): confusing wage records. 2. Send a Hindi **voice note** "मेरा जॉब कार्ड 1001 है" (or type it) -> bot reads the number back -> confirm.
3. Result: "₹6000 ... 12 दिन देर ... लगभग ₹36 ... अनुमान" -> **See calculation** (dates + formula).
4. **Make complaint** -> read -> **YES** -> "Case KH-101 saved - not yet filed" -> `status`.
5. Show `1005` -> "needs review, no amount" (shows honesty). 6. Cline segment: Plan Mode, red-to-green tests, repo.

## 6. If you get stuck
- A `reference_solution/` zip is provided separately. **Use it only to unblock after ~20 minutes stuck, never paste it as "Cline output"**, and note in `CLINE_LOG.md` what you used it for. Judges value honest Cline evidence.
- Failing test on a shared contract? Don't edit `models.py` alone - tell the team, update `SPEC.md` and the test together.
- Free-tier rate limits: keep tests offline (they are), cache demo responses, never put keys in git.

## 7. Known limitations to state openly
Rule values unverified until T1+T4 do it; sample data only; no government filing (handoff to Gram Panchayat); STT accuracy on rural accents and numbers is imperfect (hence the read-back confirmation); translations need native-speaker review; Twilio sandbox is for testing (testers must `join`, sessions expire).
