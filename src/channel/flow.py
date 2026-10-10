"""Conversation state machine - THE single entry point for every channel.   OWNER: T3

    handle_message(user_id, text=None, audio_bytes=None) -> Reply        (src.engine.models.Reply)

No provider code in here: the simulator and the Twilio webhook both call this and send reply.render().
Design (SPEC.md section 5):
  States: NEW -> LANG -> ASK_JC -> CONFIRM_JC -> RESULT -> DRAFT_REVIEW <-> EDIT_DRAFT -> DONE
  Phases (PHASES, for UIs):  LANG/ASK_JC = collecting_information, CONFIRM_JC/RESULT = awaiting_review,
                             DRAFT_REVIEW/EDIT_DRAFT = awaiting_confirmation, DONE = case_created.
  - Replies are NUMBERED: Reply(text, options=[Option(id,label)...], hint=t(lang,"reply_number")).
    The offered options are stored in the session (data["opts"]) so "1","2",... map back to ids next turn.
    Also accepted: YES/NO/CANCEL words, language names, STATUS (any state) and restart words (hi, नमस्ते...).
  - Voice: audio_bytes and no text -> src.ai.transcribe(audio, lang); None -> "retry_audio" WITHOUT changing state.
  - Job card: src.ai.extract_fields(text, lang).job_card, read back for confirmation (correction = "No" or a new
    number). Lookup: src.adapters.get_adapter().get_records(jc) -> src.engine.calculator.calculate(rec, rules) with
    the CONFIGURED rules (src.engine.rules.load_rules() = rules/delay_rules.json). Numbers come ONLY from the engine.
  - Explanation: src.ai.explain (grounded LLM rewrite or template). Calculation view: dates + formula from the
    result (never recomputed). Draft: src.ai.draft_complaint -> approve / edit / cancel.

CONSENT: a case is created ONLY when the worker, in state DRAFT_REVIEW (draft already shown), sends option
"act:approve" (its number) or a YES word themselves. Model output is never consent: the LLM only phrases text, and
a TRANSCRIBED voice note cannot approve (the worker must type/tap). Cases are SIMULATED and never filed anywhere.
Failures (adapter/engine/AI/storage) never crash the chat: the user gets a safe message and the same options.
"""
from __future__ import annotations
import logging
from typing import Optional

from src import adapters, ai, config
from src.ai.explain import template_explain
from src.ai.utils import fmt_money, normalize_digits
from src.channel import store
from src.engine import calculator
from src.engine.models import CalcResult, Option, Reply, Status
from src.engine.rules import load_rules
from src.messages import LANG_OPTIONS, t

log = logging.getLogger(__name__)

NEW, LANG, ASK_JC, CONFIRM_JC = "NEW", "LANG", "ASK_JC", "CONFIRM_JC"
RESULT, DRAFT_REVIEW, EDIT_DRAFT, DONE = "RESULT", "DRAFT_REVIEW", "EDIT_DRAFT", "DONE"
PHASES = {NEW: "new", LANG: "collecting_information", ASK_JC: "collecting_information",
          CONFIRM_JC: "awaiting_review", RESULT: "awaiting_review", DRAFT_REVIEW: "awaiting_confirmation",
          EDIT_DRAFT: "awaiting_confirmation", DONE: "case_created"}

MAX_INPUT_CHARS = 2000
YES_WORDS = {"yes", "y", "haan", "han", "ji haan", "हाँ", "हां", "जी हाँ", "जी हां"}
NO_WORDS = {"no", "n", "nahi", "nahin", "नहीं", "नही", "ना"}
CANCEL_WORDS = {"cancel", "radd", "रद्द", "रद्द करें"}
STATUS_WORDS = {"status", "स्थिति", "स्टेटस"}
RESTART_WORDS = {"hi", "hello", "hey", "namaste", "नमस्ते", "नमस्कार", "start", "restart", "menu"}
LANG_WORDS = {"hindi": "lang:hi", "हिंदी": "lang:hi", "हिन्दी": "lang:hi", "english": "lang:en", "अंग्रेज़ी": "lang:en"}
_AMOUNT_STATUSES = (Status.DELAYED, Status.UNPAID_OVERDUE)


# ---------------------------------------------------------------- small helpers
def _word(raw: str) -> str:
    return normalize_digits(raw).strip().casefold().strip(" .!?,।")


def _reply(lang: Optional[str], text: str, opts: Optional[list] = None) -> Reply:
    options = [Option(id=o[0], label=o[1]) for o in (opts or [])]
    return Reply(text=text, options=options, hint=t(lang, "reply_number") if options else "")


def _out(state: str, lang: Optional[str], data: dict, text: str, opts: Optional[list] = None):
    data["opts"] = [list(o) for o in (opts or [])]
    return state, lang, data, _reply(lang, text, data["opts"])


def _lang_opts() -> list:
    return [[oid, label] for oid, label in LANG_OPTIONS if oid.split(":", 1)[1] in config.SUPPORTED_LANGS]


def _choose(word: str, opts: list) -> Optional[str]:
    """Map the user's reply to one of the OFFERED option ids (number, yes/no word, language name, label)."""
    ids = [o[0] for o in opts]
    if word.isdigit():
        n = int(word)
        return ids[n - 1] if 1 <= n <= len(ids) else None
    candidates = []
    if word in YES_WORDS:
        candidates = ["jc:yes", "act:approve"]
    elif word in NO_WORDS:
        candidates = ["jc:no"]
    elif word in CANCEL_WORDS:
        candidates = ["act:cancel"]
    elif word in LANG_WORDS:
        candidates = [LANG_WORDS[word]]
    candidates += [o[0] for o in opts if o[1].casefold() == word]
    return next((c for c in candidates if c in ids), None)


def _results(data: dict) -> list[CalcResult]:
    return [CalcResult.model_validate(r) for r in data.get("results", [])]


def _eligible(r: CalcResult) -> bool:
    return r.status in _AMOUNT_STATUSES and r.compensation is not None


def _result_opts(lang: Optional[str], data: dict) -> list:
    opts = [] if data.get("calc_shown") else [["act:calc", t(lang, "btn_calc")]]
    if any(_eligible(r) for r in _results(data)) and not data.get("draft_blocked"):
        opts.append(["act:draft", t(lang, "btn_draft")])
    return opts + [["act:cancel", t(lang, "btn_cancel")]]


def _review_opts(lang: Optional[str]) -> list:
    return [["act:approve", t(lang, "btn_approve")], ["act:edit", t(lang, "btn_edit")],
            ["act:cancel", t(lang, "btn_cancel")]]


def _confirm_opts(lang: Optional[str]) -> list:
    return [["jc:yes", t(lang, "yes")], ["jc:no", t(lang, "no")]]


# Two texts that src/messages.py does not have yet (channel files only in this task). TODO: move to messages.py and
# have a native speaker review the Hindi.
_LOCAL_TEXT = {
    "service_error": {
        "en": "Sorry, something went wrong on our side. Nothing was saved or filed. Please try again.",
        "hi": "माफ़ कीजिए, हमारी तरफ़ कोई गड़बड़ी हुई। कुछ भी सहेजा या दर्ज नहीं हुआ। कृपया फिर से कोशिश करें।",
    },
    "approve_by_typing": {
        "en": "For your safety, please approve by typing YES or the option number - a voice note cannot approve.",
        "hi": "आपकी सुरक्षा के लिए, कृपया YES या विकल्प का नंबर लिखकर मंज़ूरी दें - आवाज़ से मंज़ूरी नहीं होती।",
    },
}


def _local(lang: Optional[str], key: str) -> str:
    texts = _LOCAL_TEXT[key]
    return texts.get(lang or config.DEFAULT_LANG) or texts["en"]


def _welcome(lang: Optional[str]) -> str:
    if lang:
        return t(lang, "welcome")
    return "\n\n".join(t(code, "welcome") for code in config.SUPPORTED_LANGS)


def _status_text(user_id: str, lang: Optional[str]) -> str:
    cases = store.list_cases(user_id)
    if not cases:
        return t(lang, "status_none")
    lines = [t(lang, "status_head")]
    for c in cases:
        label = t(lang, f"st_{c.status}")
        lines.append(t(lang, "status_line", case_id=c.case_id, jc=c.job_card_no, comp=fmt_money(c.compensation),
                       status=c.status if label == f"st_{c.status}" else label))
    return "\n".join(lines)


def _explain_safe(r: CalcResult, lang: Optional[str]) -> str:
    try:
        return ai.explain(r, lang)
    except Exception:                              # AI layer failure -> deterministic template, never a crash
        log.warning("explain failed; using template")
        return template_explain(r, lang)


# ---------------------------------------------------------------- steps
def _ask_confirm(lang, data, jc: str):
    data.update(jc=jc, results=[], calc_shown=False)
    data.pop("draft", None)
    data.pop("case", None)
    return _out(CONFIRM_JC, lang, data, t(lang, "confirm_job_card", jc=jc), _confirm_opts(lang))


def _extract_job_card(text: str, lang: Optional[str]) -> Optional[str]:
    try:
        return ai.extract_fields(text, lang).job_card
    except Exception:
        log.warning("extract_fields failed")
        return None


def _lookup(lang, data):
    jc = data["jc"]
    records = adapters.get_adapter().get_records(jc)
    if not records:
        data.update(results=[])
        text = t(lang, "not_found", jc=jc) + "\n" + t(lang, "ask_job_card")
        return _out(ASK_JC, lang, data, text)
    rules = load_rules()                           # rules/delay_rules.json - the ONLY source of due days and rate
    results = [calculator.calculate(rec, rules) for rec in records]
    data.update(results=[r.model_dump(mode="json") for r in results], calc_shown=False, draft_blocked=False)
    text = "\n\n".join(_explain_safe(r, lang) for r in results)
    return _out(RESULT, lang, data, text, _result_opts(lang, data))


def _calc_view(lang, data):
    results = _results(data)
    parts = []
    for r in results:
        if r.formula and r.compensation is not None:
            parts.append(t(lang, "calc", closed=r.closure_date or "-", due=r.due_date or "-",
                           paid=r.payment_date or t(lang, "not_paid"), days=r.delay_days, formula=r.formula))
        else:
            parts.append(t(lang, "no_calc"))
    if results and results[0].disclaimer:
        parts.append(results[0].disclaimer)      # engine disclosure, e.g. "Rule values not yet verified."
    data["calc_shown"] = True
    return _out(RESULT, lang, data, "\n\n".join(parts), _result_opts(lang, data))


def _draft(lang, data):
    eligible = [r for r in _results(data) if _eligible(r)]
    if not eligible:
        data["draft_blocked"] = True
        return _out(RESULT, lang, data, t(lang, "no_draft_needed"), _result_opts(lang, data))
    r = eligible[0]                              # one complaint (case) per wage period
    draft = ai.draft_complaint(r, lang)
    if draft == t(lang, "no_draft_needed"):
        data["draft_blocked"] = True
        return _out(RESULT, lang, data, draft, _result_opts(lang, data))
    data.update(draft=draft, case={"jc": r.job_card_no, "comp": r.compensation})
    return _show_draft(lang, data)


def _show_draft(lang, data):
    return _out(DRAFT_REVIEW, lang, data, t(lang, "draft_intro") + "\n\n" + data["draft"], _review_opts(lang))


def _approve(user_id, lang, data, from_voice: bool):
    """The ONLY place a case is created: explicit worker approval of the draft they were shown."""
    if from_voice:
        return _out(DRAFT_REVIEW, lang, data, _local(lang, "approve_by_typing"), _review_opts(lang))
    case_info, draft = data.get("case"), data.get("draft")
    if not case_info or not draft:
        return _out(NEW, lang, {}, _local(lang, "service_error"))
    case = store.create_case(user_id, case_info["jc"], draft, case_info["comp"])
    label = t(lang, f"st_{case.status}")
    text = t(lang, "approved", case_id=case.case_id, status=case.status if label == f"st_{case.status}" else label)
    return _out(DONE, lang, {"last_case": case.case_id}, text)



# ---------------------------------------------------------------- dispatcher
def _step(user_id: str, state: str, lang: Optional[str], data: dict, raw: str, from_voice: bool):
    """Pure-ish transition: (state, lang, data, input) -> (state, lang, data, Reply). Store writes only in _approve."""
    word = _word(raw)
    opts = data.get("opts", [])

    if word in STATUS_WORDS:                       # works in any state; does not change it
        return state, lang, data, _reply(lang, _status_text(user_id, lang), opts)
    if word in RESTART_WORDS or state in (NEW, DONE):
        return _out(LANG, None, {}, _welcome(None), _lang_opts())
    if word in CANCEL_WORDS:
        return _out(NEW, lang, {}, t(lang, "cancelled"))

    if state == LANG:
        choice = _choose(word, opts)
        if choice and choice.startswith("lang:"):
            lang = choice.split(":", 1)[1]
            return _out(ASK_JC, lang, {}, t(lang, "ask_job_card"))
        return _out(LANG, lang, data, t(lang, "fallback"), _lang_opts())

    if state == ASK_JC:
        jc = _extract_job_card(raw, lang)
        if jc:
            return _ask_confirm(lang, data, jc)
        return _out(ASK_JC, lang, data, t(lang, "no_job_card"))

    if state == CONFIRM_JC:
        choice = _choose(word, opts)
        if choice == "jc:yes":
            return _lookup(lang, data)
        if choice == "jc:no":
            return _out(ASK_JC, lang, data, t(lang, "ask_job_card"))
        jc = _extract_job_card(raw, lang) if not word.isdigit() or len(word) >= 3 else None
        if jc:                                     # correction: the worker typed a different number directly
            return _ask_confirm(lang, data, jc)
        return _out(CONFIRM_JC, lang, data, t(lang, "fallback"), opts)

    if state == RESULT:
        choice = _choose(word, opts)
        if choice == "act:calc":
            return _calc_view(lang, data)
        if choice == "act:draft":
            return _draft(lang, data)
        if choice == "act:cancel":
            return _out(NEW, lang, {}, t(lang, "cancelled"))
        return _out(RESULT, lang, data, t(lang, "fallback"), opts)

    if state == DRAFT_REVIEW:
        choice = _choose(word, opts)
        if choice == "act:approve":
            return _approve(user_id, lang, data, from_voice)
        if choice == "act:edit":
            return _out(EDIT_DRAFT, lang, data, t(lang, "edit_prompt"))
        if choice == "act:cancel":
            return _out(NEW, lang, {}, t(lang, "cancelled"))
        return _out(DRAFT_REVIEW, lang, data, t(lang, "fallback"), opts)

    if state == EDIT_DRAFT:
        new_text = raw.strip()
        if not new_text:
            return _out(EDIT_DRAFT, lang, data, t(lang, "edit_prompt"))
        data["draft"] = new_text[:store.MAX_COMPLAINT_CHARS]   # the worker's own words; amount stays the engine's
        return _show_draft(lang, data)

    return _out(LANG, None, {}, _welcome(None), _lang_opts())   # unknown/legacy state -> safe restart


def handle_message(user_id: str, text: Optional[str] = None, audio_bytes: Optional[bytes] = None) -> Reply:
    try:
        session = store.get_session(user_id)
    except store.StoreError:
        log.error("session load failed")
        return _reply(None, _local(None, "service_error"))
    state, lang, data = session["state"], session["lang"], session["data"]

    from_voice = False
    if (text is None or not text.strip()) and audio_bytes:
        try:
            text = ai.transcribe(audio_bytes, lang)
        except Exception:
            text = None
        if not text or not text.strip():
            return _reply(lang, t(lang, "retry_audio"), data.get("opts", []))   # state unchanged
        from_voice = True
    raw = (text or "")[:MAX_INPUT_CHARS]

    try:
        new_state, new_lang, new_data, reply = _step(user_id, state, lang, data, raw, from_voice)
    except Exception:                                # adapter / engine / AI / storage failure
        log.exception("conversation step failed in state %s", state)
        return _reply(lang, _local(lang, "service_error"), data.get("opts", []))   # same options, state kept

    try:
        store.save_session(user_id, new_state, new_lang, new_data)
    except store.StoreError:
        log.error("session save failed")
    return reply


def session_view(user_id: str) -> dict:
    """Read-only snapshot for UIs (simulator): phase, language, job card, engine results, draft. No side effects."""
    s = store.get_session(user_id)
    data = s["data"]
    return {"state": s["state"], "phase": PHASES.get(s["state"], "new"), "lang": s["lang"], "job_card": data.get("jc"),
            "results": _results(data), "draft": data.get("draft"), "last_case": data.get("last_case")}

