"""Conversation channels. Public entry point: src.channel.flow.handle_message (used by the simulator and webhook).

Kept import-free on purpose: importing src.channel must not pull in FastAPI / Streamlit or create import cycles.
Import the submodules directly:  from src.channel import flow, store
"""
__all__ = ["flow", "store"]

