-- Создание таблицы названий команд по турнирам
CREATE TABLE IF NOT EXISTS tournament_team_names (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(tournament_id, name)
);

-- Создание таблицы матчей
CREATE TABLE IF NOT EXISTS matches_simple (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    stage TEXT,
    team_home_name TEXT NOT NULL,
    team_away_name TEXT NOT NULL,
    score_home INTEGER,
    score_away INTEGER,
    status TEXT DEFAULT 'scheduled' -- scheduled|finished|wo
);
