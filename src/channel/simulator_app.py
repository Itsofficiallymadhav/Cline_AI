"""Streamlit chat simulator calling handle_message (no Twilio needed).   OWNER: T3

Run:  streamlit run src/channel/simulator_app.py
TODO(T3): a chat page that
  - keeps a message log in st.session_state, shows user/bot bubbles (st.chat_message), uses st.chat_input
  - sends every input to src.channel.flow.handle_message(user_id, text=..., audio_bytes=...) and shows reply.render()
  - draws reply.options as clickable buttons that send the option NUMBER (re-read the options AFTER sending, or buttons go stale)
  - has a sidebar: simulated user id, reset, and a voice-note file uploader
  - starts the conversation by sending "hi"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

st.title("KaamKaHisab - WhatsApp simulator")
st.info("TODO(T3): implement the simulator - see the docstring at the top of this file.")
