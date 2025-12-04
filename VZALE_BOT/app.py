"""Minimal HTTP API layer that reuses the same SQLite logic as the bot.

How to run locally:
- Put BOT_TOKEN, DB_PATH (optional), API_SECRET (optional) in a .env file next to this script.
- Start the API: `uvicorn app:app --reload` or `python app.py`.
The exported `app` variable can be used by ASGI servers on shared hosting (e.g. Beget).
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import uvicorn

from config import API_SECRET, DB_PATH
from db import get_user_by_telegram_id

app = FastAPI(title="VZALE Bot API", version="1.0.0")


@app.get("/health")
async def health() -> dict[str, str]:
    """Health-check endpoint."""
    return {"status": "ok"}


@app.get("/api/user/by-telegram-id")
async def user_by_telegram_id(telegram_id: int = Query(..., description="Telegram user id")) -> JSONResponse:
    """Fetch a user using the same SQLite database as the bot."""
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return JSONResponse({"user": user})


if __name__ == "__main__":
    # Allow `python app.py` for quick local testing alongside the bot.
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
