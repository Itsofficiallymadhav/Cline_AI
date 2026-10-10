# Cline log (evidence for the demo + README)

Add one entry per Cline task you accept. Keep it honest: what you asked, what the plan was, what you changed, test result.

| # | Who | Mode | Prompt (short) | Plan changes you made | Tests before -> after | Commit |
|---|-----|------|----------------|-----------------------|-----------------------|--------|
| 1 | T1 | Plan -> Act | Implement calculator.py ... | e.g. asked it to use Decimal | 14 failing -> 0 failing | abc123 |
| 2 | T2 | Plan -> Act | Implement src/adapters/sample.py (SampleAdapter) | Cline wrote SampleAdapter: loads data/sample_records.json into WorkerRecord objects once in `__init__`; `get_records()` returns [] for blank or unknown job cards. Problem: pip install stalled on a slow network; Cline then tried to write a fake pydantic stub and custom Python harnesses in the terminal, and the terminal got garbled. Human intervention: I stopped the task, rejected the stub approach, fixed the install myself in .venv and reviewed the adapter code. Lesson: tell Cline not to stub packages or write custom harnesses, and check the environment works before starting Cline. | Not recorded -> `python -m pytest tests/test_adapter.py -q`: 1 passed, 2 failed (both NotImplementedError from engine/calculator.py, the next task) | Not recorded |

## Screen recordings to capture
- [ ] First Plan Mode session (Cline proposes the plan, you correct it)
- [ ] A failing-tests -> passing-tests run
- [ ] Cline-in-product moment (if required by the hackathon)
