"""Full HTTP API for the VZALE site backed by the bot's SQLite database."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from db import (
    get_all_matches,
    get_all_teams,
    get_all_tournaments,
    get_last_team_for_user,
    get_team_by_id,
    get_teams_for_tournament,
    get_user_by_telegram_id,
)

app = FastAPI(title="VZALE Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _split_full_name(full_name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not full_name:
        return None, None
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


@app.get("/health")
async def health() -> dict[str, str]:
    """Health-check endpoint."""
    return {"status": "ok"}


@app.get("/api/tournaments")
async def api_tournaments() -> JSONResponse:
    try:
        tournaments = await get_all_tournaments()
        return JSONResponse(tournaments)
    except Exception as exc:  # pragma: no cover - defensive
        print("API error: /api/tournaments", exc)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@app.get("/api/teams")
async def api_teams() -> JSONResponse:
    try:
        teams = await get_all_teams()
        return JSONResponse(teams)
    except Exception as exc:  # pragma: no cover - defensive
        print("API error: /api/teams", exc)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@app.get("/api/matches")
async def api_matches() -> JSONResponse:
    try:
        matches = await get_all_matches()
        return JSONResponse(matches)
    except Exception as exc:  # pragma: no cover - defensive
        print("API error: /api/matches", exc)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@app.get("/api/users/{telegram_id}/profile")
async def api_user_profile(telegram_id: int) -> JSONResponse:
    try:
        user = await get_user_by_telegram_id(telegram_id)
        if not user:
            return JSONResponse({"error": "User not found"}, status_code=404)

        first_name, last_name = _split_full_name(user.get("full_name"))
        last_team = await get_last_team_for_user(telegram_id)
        profile: dict[str, Any] = {
            "id": telegram_id,
            "first_name": first_name,
            "last_name": last_name,
            "username": user.get("username"),
            "last_team_id": last_team.get("team_id") if last_team else None,
            "last_tournament_id": last_team.get("tournament_id") if last_team else user.get("current_tournament_id"),
        }
        return JSONResponse(profile)
    except Exception as exc:  # pragma: no cover - defensive
        print("API error: /api/users/{telegram_id}/profile", exc)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@app.get("/api/users/{telegram_id}/last-team")
async def api_user_last_team(telegram_id: int) -> JSONResponse:
    try:
        last_team = await get_last_team_for_user(telegram_id)
        if not last_team:
            return JSONResponse(content=None)

        team = await get_team_by_id(last_team["team_id"])
        response = {
            "team_id": last_team["team_id"],
            "team_name": team.get("name") if team else None,
        }
        return JSONResponse(response)
    except Exception as exc:  # pragma: no cover - defensive
        print("API error: /api/users/{telegram_id}/last-team", exc)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@app.get("/api/tournaments/{tournament_id}/teams")
async def api_tournament_teams(tournament_id: int) -> JSONResponse:
    try:
        teams = await get_teams_for_tournament(tournament_id)
        return JSONResponse(teams)
    except Exception as exc:  # pragma: no cover - defensive
        print("API error: /api/tournaments/{tournament_id}/teams", exc)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
