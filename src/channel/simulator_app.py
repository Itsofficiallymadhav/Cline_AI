"""Streamlit chat simulator calling handle_message (no Twilio needed).   OWNER: T3

Run (from the repo root):  streamlit run src/channel/simulator_app.py

A thin UI over the SAME flow the WhatsApp webhook uses. It holds no business logic: every message, option button and
confirmation is sent to src.channel.flow.handle_message; numbers are only DISPLAYED from the engine results that the
flow stored (src.channel.flow.session_view). Consent stays in the flow: the approve button just sends the option
number, exactly like typing it on WhatsApp.
  - message log in st.session_state, user/bot bubbles (st.chat_message), st.chat_input (text always works)
  - reply.options as buttons that send the option NUMBER (options are re-read after each send)
  - sidebar: simulated user id, reset, language shortcut, optional voice-note upload
  - starts the conversation by sending "hi"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from src import config  # noqa: E402
from src.ai.utils import fmt_money  # noqa: E402
from src.channel import flow, store  # noqa: E402
from src.messages import t  # noqa: E402

APP_NAME = "KaamKaHisab"
PURPOSE = ("Check delayed MNREGA wages, see an illustrative compensation estimate and prepare a complaint draft "
           "for your own review.")
PHASE_LABELS = {"new": "Start", "collecting_information": "1. Your details", "awaiting_review": "2. Review result",
                "awaiting_confirmation": "3. Review complaint", "case_created": "4. Case saved (simulated)"}

st.set_page_config(page_title=f"{APP_NAME} simulator", page_icon="💬", layout="centered")


# ---------------------------------------------------------------- state + sending
def _init() -> None:
    st.session_state.setdefault("user_id", "sim-user-1")
    st.session_state.setdefault("log", [])          # list of (role, text)
    st.session_state.setdefault("options", [])      # options of the LAST bot reply
    st.session_state.setdefault("error", None)


def send(text=None, audio=None, shown=None) -> None:
    """The only way the UI talks to the app: one call to flow.handle_message."""
    st.session_state.error = None
    st.session_state.log.append(("user", shown or text or "🎤 voice note"))
    try:
        reply = flow.handle_message(st.session_state.user_id, text=text, audio_bytes=audio)
    except Exception as e:                           # flow guards itself; show something understandable anyway
        st.session_state.error = f"The app could not process that message ({type(e).__name__}). Nothing was saved."
        return
    st.session_state.log.append(("assistant", reply.text))
    st.session_state.options = [(i, o.label) for i, o in enumerate(reply.options, 1)]


def reset_user() -> None:
    try:
        store.reset_session(st.session_state.user_id)
    except store.StoreError:
        st.session_state.error = "Could not reset the conversation (storage unavailable)."
    st.session_state.log, st.session_state.options = [], []
    send("hi")


_init()
if not st.session_state.log:
    send("hi")




# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Simulator settings")
    new_id = st.text_input("Simulated user id", value=st.session_state.user_id,
                           help="Each id is a separate worker with its own conversation and cases.")
    if new_id.strip() and new_id.strip() != st.session_state.user_id:
        st.session_state.user_id = new_id.strip()
        st.session_state.log, st.session_state.options = [], []
        send("hi")
    if st.button("Reset conversation", use_container_width=True):
        reset_user()
    st.caption("Language: choose it in the chat (1 हिन्दी / 2 English) or here:")
    c1, c2 = st.columns(2)
    if c1.button("हिन्दी", use_container_width=True):
        send("hindi", shown="हिन्दी")
    if c2.button("English", use_container_width=True):
        send("english", shown="English")

    st.divider()
    st.subheader("Voice note (optional)")
    if config.GROQ_API_KEY:
        st.caption("Upload a voice note (ogg, mp3, wav, m4a). For safety, approval must still be typed or tapped.")
        audio = st.file_uploader("Voice note", type=["ogg", "opus", "mp3", "wav", "m4a", "webm"],
                                 label_visibility="collapsed")
        if audio is not None and st.button("Send voice note", use_container_width=True):
            send(audio=audio.getvalue())
    else:
        st.caption("Speech recognition is not configured (no GROQ_API_KEY). Please type your messages - "
                   "text input always works.")

    st.divider()
    st.caption("Commands: **status** lists your cases · **cancel** stops · **hi** restarts.")


# ---------------------------------------------------------------- header
st.title(f"{APP_NAME} 💬")
st.write(PURPOSE)
st.warning("**Demo / prototype.** Uses fictional sample records (try job cards 1001-1006, 9999). Estimates are "
           "illustrative, not legal advice. Cases are **simulated** and are **NOT** filed with any government system.",
           icon="⚠️")
try:
    view = flow.session_view(st.session_state.user_id)
except Exception:
    view = None
    st.error("Could not read the conversation state (storage unavailable). The chat may not work.")

_PHASE_ORDER = ["new", "collecting_information", "awaiting_review", "awaiting_confirmation", "case_created"]
if view:
    st.progress(_PHASE_ORDER.index(view["phase"]) / 4 if view["phase"] in _PHASE_ORDER else 0.0,
                text=PHASE_LABELS.get(view["phase"], ""))
if st.session_state.error:
    st.error(st.session_state.error)


# ---------------------------------------------------------------- details panels (display only, no calculation)
if view and view["job_card"]:
    with st.expander("Your details (review)", expanded=view["phase"] == "awaiting_review"):
        st.write(f"**Job card:** {view['job_card']}")
        st.caption("Wrong number? Reply **2 / No** to the read-back question, or type the correct number. "
                   "Wrong record data must be corrected by your Gram Panchayat; this app cannot change records.")
        for r in view["results"]:
            st.write(f"**Status:** {t(view['lang'], 'rs_' + r.status.value)}"
                     + (f" · **Delay:** {r.delay_days} days" if r.delay_days else ""))
            if r.compensation is not None:
                st.metric("Illustrative compensation estimate", f"₹{fmt_money(r.compensation)}")
                st.write(f"Wage: ₹{fmt_money(r.wage_amount)} · Due: {r.due_date or '-'} · "
                         f"Paid: {r.payment_date or 'not paid yet'}")
                if r.formula:
                    st.code(f"Formula: {r.formula}", language=None)
            if r.flags:
                st.info("Needs officer review: " + ", ".join(t(view["lang"], "flag_" + f.value) for f in r.flags)
                        + ". No amount is calculated.")
            st.caption(f"Assumptions (from rules/delay_rules.json): due {r.due_days} days after the muster roll "
                       f"closes; {r.rate_per_day} of the wage per day of delay. {r.disclaimer}"
                       + ("" if r.rule_verified else f" Source: {r.rule_source or '-'}"))

if view and view["draft"] and view["phase"] == "awaiting_confirmation":
    with st.expander("Complaint draft (read before approving)", expanded=True):
        st.text(view["draft"])
        st.caption("Nothing is saved until you choose **YES - approve complaint** below.")


# ---------------------------------------------------------------- chat
for role, text in st.session_state.log:
    with st.chat_message(role):
        st.text(text)                                  # plain text: no markdown/HTML injection from user input

if st.session_state.options:
    for i, label in st.session_state.options:
        if st.button(f"{i}. {label}", key=f"opt-{len(st.session_state.log)}-{i}", use_container_width=True):
            send(str(i), shown=f"{i}. {label}")
            st.rerun()                                 # redraw with the NEW options (avoid stale buttons)

prompt = st.chat_input("Type a message, a number, or 'status'")
if prompt:
    send(prompt)
    st.rerun()


# ---------------------------------------------------------------- simulated cases + status history
try:
    cases = store.list_cases(st.session_state.user_id)
except store.StoreError:
    cases = []
    st.error("Could not load saved cases (storage unavailable).")
if cases:
    st.divider()
    st.subheader("Your simulated cases")
    case_lang = view["lang"] if view else None
    for c in reversed(cases):
        with st.container(border=True):
            st.write(f"**{c.case_id}** · job card {c.job_card_no} · ₹{fmt_money(c.compensation)} (estimate) · "
                     f"status: **{t(case_lang, 'st_' + c.status)}**")
            st.caption("SIMULATED case for the demo - NOT filed on any government portal. "
                       "Hand the complaint to your Gram Panchayat.")
            try:
                for ev in store.get_case_history(st.session_state.user_id, c.case_id):
                    st.caption(f"{ev['at']} - {t(case_lang, 'st_' + ev['status'])} - {ev['note']}")
            except store.StoreError:
                st.caption("Status history unavailable.")

