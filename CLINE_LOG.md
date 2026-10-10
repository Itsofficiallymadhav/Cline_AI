#	Who	Mode	Prompt (short)	Plan changes you made	Tests before -> after	Commit
1	T1	Plan -> Act	Finalize calculator spec; implement calculator, SampleAdapter and rule metadata	Human approved 9 safety and scope decisions; synthetic demo rule only; no tests weakened	38 passed in focused tests; full run had 11 failures from unfinished T3 flow and missing dependencies	not committed (local only)
2	T1	Act	Finalize and verify calculator	Fixed non-finite wage/payment handling and evidence-source labels; added 2 tests	40 passed, 0 failed in calculator + safety + adapter tests	not committed at that point
3	T1	Act	Review T1 diff and clean up tests	Removed stray assertion and duplicate test; no calculator logic changed and no coverage lost	Existing relevant tests still passed	not committed at that point
4	T1	Act	Summarize deterministic wage calculator before commit	Documented Decimal calculation, review gates, rule metadata, synthetic-only limitations and safety tests	40 passed, 0 failed in calculator + safety + adapter tests	not committed at that point
5	T1	Act	Audit repository before commit	Audited tracked/untracked/staged/ignored files; left Madhav-owned adapter untouched; recorded ownership and commit status	37 passed, 0 failed in calculator + safety tests	not committed
6	T1	Act	Separate adapter tests from calculator safety tests	Moved two adapter tests to a handoff document; calculator-only suite retained 21 safety tests	35 passed, 0 failed in calculator + safety tests	not committed
7	T1	Act	Calculator cleanup and validation	Finalized calculator, rule metadata, illustrative rule labeling and 21 calculator safety tests	35 passed, 0 failed in calculator + safety tests	1fc7894
8	T4 (integrator)	Plan -> Act	Audit origin/main; fix channel texts, Hindi calc view, voice notes without keys, simulator labels; add regression tests	Phase 0 cancelled by human; main already integrated; human approved decisions A-E	257 passed -> 260 passed (3 new tests, none changed)	6d7f6f3
9	T4 (integrator)	Act	Gemini default model, money formatting, multi-part LLM replies, .gitignore / untrack .DS_Store	Updated Gemini default; fixed exponent formatting; retained compatibility alias	260 passed -> 260 passed	6e6e638
10	T4 (integrator)	Act	SPEC.md rule gating, test list, rules.py ownership; README optional keys and demo date	Documented stricter engine behaviour; no code change	260 passed -> 260 passed	see git log


Entry 1 details (what actually happened)
- Files changed: src/engine/calculator.py (Decimal calculator), src/adapters/sample.py (SampleAdapter), src/engine/rules.py (optional fields: scheme, version, effective_from/to, delay_start_offset_days, synthetic_demo), rules/delay_rules.json (labelled DEMO_ILLUSTRATIVE, synthetic_demo: true, last_verified still null), new tests/test_calculator_safety.py. models.py, flags and existing tests untouched.
- Cline mistake (partially fixed at the time): the second half of the new test file was inserted at the wrong line, which caused an IndentationError at collection (found from the real pytest output). Cline re-added the two displaced tests in the right place but did NOT delete the misplaced originals, leaving a stray assertion inside test_adapter_returns_copies() and a duplicate test_pending_with_payment_details_is_conflict() at the end of the file. The tests still passed, so the duplication went unnoticed until the final T1 diff review (see Entry 3).
- Rule status: still UNVERIFIED. The 15-day / 0.0005 values and the day-counting convention were NOT checked against official text; web sources consulted were secondary only. Human verification against the gazetted rule is still required.
- Limitation: the engine cannot tell real from synthetic records; the safety gate is the rule file (synthetic_demo or last_verified). Real claims must not be run until a verified rule set for the applicable scheme exists.
- Human review of diffs: pending (to be ticked by the team member who reviews the diff).
Entry 2 - T1 finalize & verify calculator (Act)
- User confirmed role: T1 only. Scope: calculator, rules, sample adapter, T1 tests. No AI/flow/webhook/UI files touched.
- Review found 2 genuine defects via a probe script (real output): (a) NaN/inf daily_wage_rate or inf payment_amount raised decimal.InvalidOperation instead of NEEDS_REVIEW; (b) missing-closure / missing-wage review reasons were tagged payment_record instead of muster_roll in evidence.
- Fix in src/engine/calculator.py: _positive_finite() guard + finite check on payment amount (=> missing_wage_data, NEEDS_REVIEW); flag() takes an evidence source. Added 2 tests to tests/test_calculator_safety.py. No existing test changed.
- Tests: pytest -q tests/test_calculator.py tests/test_calculator_safety.py tests/test_adapter.py = 40 passed, 0 failed.
- rules/delay_rules.json unchanged: still DEMO_ILLUSTRATIVE, synthetic_demo: true, last_verified: null. Not legally verified. Not committed.
Entry 3 - T1 diff review and test-file cleanup (Act, human-approved)
- Found during the final T1 diff review: leftover code from the Entry 1 bad insert (stray assertion in test_adapter_returns_copies(), duplicate test_pending_with_payment_details_is_conflict()). Both copies were identical, so no check was lost.
- Removed the stray assertion and the duplicate definition; kept the original test (still covers pending-with-payment-details) and the unknown-status test. No calculator logic changed, no test weakened. Corrected Entry 1's wording and role.
Entry 4 - 2026-10-10 - T1 deterministic wage calculator: summary before commit
Completed (in the local working tree, branch samarth)
- src/engine/calculator.py: deterministic calculate(rec, rules=None, today=None) -> CalcResult. No LLM, no network, no src.ai imports.
  - Money in Decimal (converted via str()), rounded to cents with ROUND_HALF_UP; float only at the CalcResult boundary.
  - Gross wages = days_worked x daily_wage_rate; due date = closure + due_days; delay days = max(0, end date - due date - delay_start_offset_days), end date = payment date if fully paid, else the reference date.
  - Compensation = gross x rate x delay days, only for delayed / unpaid_overdue; formula string e.g. 6000 x 0.0005 x 12 = 36.
  - Outstanding wages reported as an Evidence entry (no model change).
  - NEEDS_REVIEW (no amounts) for: missing closure date, missing / non-positive / non-finite (NaN, inf) wage or payment values, unknown payment status, failed payment, partial or mismatched payment, success without date or amount, pending with payment details, payment before closure, future dates, unusable rule values, closure outside the rule's effective_from / effective_to window, and a rule that is neither verified nor marked synthetic_demo.
  - All checks run together; existing flags reused; each review reason recorded as Evidence with the correct source (muster_roll, payment_record or rule).
- src/engine/rules.py: optional, backward-compatible rule fields (scheme, version, effective_from, effective_to, delay_start_offset_days, synthetic_demo).
- rules/delay_rules.json: values unchanged (15 days, 0.0005); labelled DEMO_ILLUSTRATIVE, synthetic_demo: true, last_verified: null.
- tests/test_calculator_safety.py: 23 new tests (rule safety, review cases, non-finite values, evidence sources, Decimal rounding, formula text, outstanding wages, adapter edge cases).
Tests (re-run 2026-10-10 before writing this entry)
- C:\Users\samar\kkh_venv\Scripts\python.exe -m pytest -q tests/test_calculator.py tests/test_calculator_safety.py tests/test_adapter.py -> 40 passed, 0 failed (14 + 23 + 3).
- Existing tests in tests/test_calculator.py and tests/test_adapter.py unchanged.
Limitations
- For synthetic / demo use only. The rule values and day-counting convention are illustrative and NOT verified against official MGNREGA or VB-G RAM G text. Results are estimates, not legal determinations.
- The engine cannot tell real from synthetic records; the safety gate is the rule file.
- Partial payments cannot be modelled (one payment per record) and always go to NEEDS_REVIEW.
Remaining
- Human review of the diff: pending.
- Human verification of the rule against the gazetted text, then setting last_verified.
- Ownership of src/adapters/sample.py and the adapter tests to be confirmed before committing.
- Commit / push: not done at the time of writing.
Entry 5 - 2026-10-10 - T1 repository audit before commit (Act, human-requested)
- Audited every folder (tracked, untracked, staged, ignored). Branch samarth, nothing staged, no stash.
- No files reverted or deleted:
  - src/adapters/sample.py: Cline wrote this in Entry 1, but it belongs to Madhav's adapter work (his own version is on origin/madhav). Left untouched on the user's instruction. It stays uncommitted and is NOT part of the T1 commit.
  - __pycache__/ and .pytest_cache/: generated test-run artifacts, already git-ignored. Not reliably attributable to Cline, so left in place.
- Kept as T1 calculator work: src/engine/calculator.py, src/engine/rules.py (rule fields used by the calculator; ownership approval pending), rules/delay_rules.json (T1-owned per SPEC.md; still illustrative and unverified), tests/test_calculator_safety.py (contains 2 adapter tests still to be agreed with Madhav), and this log.
- Tests: C:\Users\samar\kkh_venv\Scripts\python.exe -m pytest -q tests/test_calculator.py tests/test_calculator_safety.py -> 37 passed, 0 failed (14 + 23; run after the audit, before this line was written).
- Commit / push: not done. Human review of the final diff: pending.
Entry 6 - 2026-10-10 - T1 adapter tests separated (Act, human-approved Option 1)
- Removed test_adapter_unknown_blank_and_whitespace and test_adapter_returns_copies from tests/test_calculator_safety.py (plus their now-unused json / SampleAdapter imports). The file now holds 21 calculator-only tests.
- Not deleted: both tests preserved verbatim in docs/handoff_adapter_tests_for_T1_adapter_owner.md for Madhav / T4 to place in tests/test_adapter.py. Observed: test_adapter_returns_copies fails against the origin/madhav adapter (it returns stored objects, not copies). Not changed by T1.
- src/adapters/sample.py not modified or staged.
- Tests: C:\Users\samar\kkh_venv\Scripts\python.exe -m pytest -q tests/test_calculator.py tests/test_calculator_safety.py -> 35 passed, 0 failed (14 + 21). The same 35 also pass in a clean copy of HEAD with only the 4 T1 files applied and the original stub adapter, so the T1 commit does not depend on any adapter.
- Correction to Entry 4: "23 new tests" there included the 2 adapter tests; the calculator file now has 21.
- Open: src/engine/rules.py ownership is not in SPEC.md (team agreement needed); this log is T4-owned and conflicts with the origin/madhav row 2 (coordinate with T4 at merge). Commit / push: not done.
Entry 7 - 2026-10-10 - T1 calculator cleanup and validation (Act)
Changes (as committed in 1fc7894)
- src/engine/calculator.py:
  - Deterministic calculate(rec, rules=None, today=None) -> CalcResult, with Decimal maths and cent-level ROUND_HALF_UP rounding.
  - Computes due date, delay days (with delay_start_offset_days), compensation for delayed / unpaid_overdue only, and outstanding wages as evidence.
  - NEEDS_REVIEW with no amounts for missing, conflicting, non-finite or inapplicable inputs and rules.
  - Review reasons carry their correct evidence source.
  - No LLM, no network, no src.ai imports.
- src/engine/rules.py: six optional, backward-compatible fields (scheme, version, effective_from, effective_to, delay_start_offset_days, synthetic_demo). These are needed by the calculator. SPEC.md lists no owner for this file, so team agreement is still needed.
- rules/delay_rules.json:
  - Values unchanged.
  - Labelled DEMO_ILLUSTRATIVE with synthetic_demo: true, last_verified: null, and a note that the values must not be applied to real claims.
- tests/test_calculator_safety.py: 21 calculator-only safety tests.
- Adapter tests: test_adapter_unknown_blank_and_whitespace and test_adapter_returns_copies were moved out of this file. They are preserved verbatim in docs/handoff_adapter_tests_for_T1_adapter_owner.md for coordination with Madhav. They are NOT part of the calculator suite and were not run as part of it.
Tests (re-run before writing this entry)
- C:\Users\samar\kkh_venv\Scripts\python.exe -m pytest -q tests/test_calculator.py tests/test_calculator_safety.py -> 35 passed, 0 failed (14 existing calculator tests + 21 calculator safety tests).
- This is the calculator suite only. It is not a claim that all project tests pass: the AI, flow and webhook tests belong to other owners and were not part of this run.
Limitations
- The 15-day deadline and the 0.0005 daily rate are illustrative and NOT verified against the official rules of any scheme.
- The calculator is for synthetic / demo use only. It must not be used for real claims until the applicable scheme rules have been verified by a human and last_verified is set.
Git state (checked with git, not assumed)
- Commit 1fc7894 "Finalize deterministic wage calculator" (author samarthh03) is on branch samarth. Its parent is 0788436.
- It contains exactly the 4 files above. git ls-remote shows origin/samarth at 1fc7894, so it has been pushed.
- This log entry, src/adapters/sample.py and the handoff file are NOT in that commit; they remain uncommitted.
Pending
- Human review of the diff: pending.
- src/adapters/sample.py: Madhav's area. Not modified in this step and not committed.
- This log is shared / T4-owned and conflicts with Madhav's row 2 on origin/madhav. Coordinate with T4 before this log change is committed; do not overwrite his entry.
Entries 8-10 - 2026-10-10 - Integration pass on main (T4, Plan -> Act)
- Start: main = origin/main = 844faff, clean tree, 257 passed. Phase 0 (fetch/merge) cancelled by the human; madhav skipped (its sample.py is already on main; its row 2 is kept on that branch).
- Entry 8 (6d7f6f3): service_error, approve_by_typing, unsupported_media, voice_unavailable, rule_unverified, demo_rule, st_*, rs_* keys added to src/messages.py (en + hi); flow.py _LOCAL_TEXT and twilio_webhook.py _UNSUPPORTED_MEDIA removed; calc view shows translated rule notes; voice notes without GROQ_API_KEY or Twilio REST credentials get an immediate "please type" reply; simulator shows labels instead of raw codes; warning when the auth token is set without PUBLIC_BASE_URL. New tests/test_integration_regressions.py (3 tests).
- Entry 9 (6e6e638): GEMINI_MODEL default gemini-3.8-flash; fmt_money never prints 1e+06 (explain._money kept as an alias, complaint.py imports fmt_money); llm.py joins all text parts; .venv/ + .DS_Store ignored, .DS_Store untracked.
- Entry 10: SPEC.md section 3/4/6/7 and README updated (docs only).
- Not changed: calculator, rules file, models, any existing test. Hindi wording of the new keys needs a native speaker's check. No live API calls were made. Not pushed.
- Open: tests/test_calculator_safety.py line 2 and Entries 6-7 mention docs/handoff_adapter_tests_for_T1_adapter_owner.md, which is not in the repo.
Screen recordings to capture
- First Plan Mode session (Cline proposes the plan, you correct it)
- A failing-tests -> passing-tests run
- Cline-in-product moment (if required by the hackathon)