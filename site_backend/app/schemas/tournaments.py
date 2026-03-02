from pydantic import BaseModel


class TournamentOut(BaseModel):
    id: int
    name: str
    date_start: str | None = None
    venue: str | None = None
    status: str


class TournamentInfoSectionOut(BaseModel):
    section: str
    content: str | None = None
    updated_at: str | None = None


class StandingOut(BaseModel):
    team_name: str
    games: int
    wins: int
    losses: int
    points_for: int
    points_against: int
    diff: int


class MatchOut(BaseModel):
    id: int
    stage: str | None = None
    team_home_name: str
    team_away_name: str
    score_home: int | None = None
    score_away: int | None = None
    status: str
