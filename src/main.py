"""FastAPI app.  Run:  uvicorn src.main:app --port 8000   then expose with:  ngrok http 8000  (or cloudflared)."""
from fastapi import FastAPI

from src.channel.twilio_webhook import router as twilio_router

app = FastAPI(title="KaamKaHisab")
app.include_router(twilio_router)


@app.get("/health")
def health():
    return {"ok": True}
