CREATE TABLE IF NOT EXISTS tournaments (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    date_start TEXT,
    venue TEXT,
    status TEXT DEFAULT 'draft',
    settings_json TEXT,
    lock_rosters_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    full_name TEXT,
    team TEXT,
    current_tournament_id BIGINT
);

CREATE TABLE IF NOT EXISTS teams (
    id BIGSERIAL PRIMARY KEY,
    team_name TEXT,
    member_id BIGINT,
    member_name TEXT
);

CREATE TABLE IF NOT EXISTS team_security (
    team_name TEXT PRIMARY KEY,
    invite_code TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS free_agents (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    name TEXT,
    info TEXT
);

CREATE TABLE IF NOT EXISTS tournaments_info_placeholder (
    id BIGSERIAL PRIMARY KEY
);
DROP TABLE IF EXISTS tournaments_info_placeholder;

CREATE TABLE IF NOT EXISTS teams_new (
    id BIGSERIAL PRIMARY KEY,
    tournament_id BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    captain_user_id BIGINT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id BIGINT NOT NULL REFERENCES teams_new(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    role TEXT DEFAULT 'player',
    status TEXT DEFAULT 'confirmed',
    tournament_id BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, user_id)
);

CREATE TABLE IF NOT EXISTS free_agents_new (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tournament_id BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    profile_json TEXT,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS team_security_new (
    tournament_id BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    team_id BIGINT NOT NULL REFERENCES teams_new(id) ON DELETE CASCADE,
    invite_code TEXT NOT NULL UNIQUE,
    PRIMARY KEY (tournament_id, team_id)
);

CREATE TABLE IF NOT EXISTS tournament_info (
    tournament_id BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    section TEXT NOT NULL,
    content TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tournament_id, section)
);

CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    tournament_id BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    stage TEXT,
    group_name TEXT,
    round TEXT,
    court TEXT,
    start_at TEXT,
    team_home_id BIGINT NOT NULL REFERENCES teams_new(id) ON DELETE CASCADE,
    team_away_id BIGINT NOT NULL REFERENCES teams_new(id) ON DELETE CASCADE,
    score_home INTEGER,
    score_away INTEGER,
    status TEXT DEFAULT 'scheduled'
);

CREATE TABLE IF NOT EXISTS standings (
    tournament_id BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    team_id BIGINT NOT NULL REFERENCES teams_new(id) ON DELETE CASCADE,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    points_for INTEGER DEFAULT 0,
    points_against INTEGER DEFAULT 0,
    diff INTEGER DEFAULT 0,
    win_pct DOUBLE PRECISION DEFAULT 0,
    PRIMARY KEY (tournament_id, team_id)
);

CREATE TABLE IF NOT EXISTS polls_group (
    group_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    options TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    is_closed INTEGER DEFAULT 0,
    tournament_id BIGINT
);

CREATE TABLE IF NOT EXISTS polls (
    poll_id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    question TEXT NOT NULL,
    options TEXT NOT NULL,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    tournament_id BIGINT
);

CREATE TABLE IF NOT EXISTS poll_votes (
    poll_id TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    option_id INTEGER NOT NULL,
    PRIMARY KEY (poll_id, user_id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    text TEXT NOT NULL,
    status TEXT DEFAULT 'new',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    tournament_id BIGINT
);

CREATE TABLE IF NOT EXISTS tournament_team_names (
    id BIGSERIAL PRIMARY KEY,
    tournament_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    paid INTEGER DEFAULT 0,
    UNIQUE (tournament_id, name)
);

CREATE TABLE IF NOT EXISTS matches_simple (
    id BIGSERIAL PRIMARY KEY,
    tournament_id BIGINT NOT NULL,
    stage TEXT,
    team_home_name TEXT NOT NULL,
    team_away_name TEXT NOT NULL,
    score_home INTEGER,
    score_away INTEGER,
    status TEXT DEFAULT 'scheduled'
);

CREATE TABLE IF NOT EXISTS player_payments (
    user_id BIGINT NOT NULL,
    tournament_id BIGINT NOT NULL,
    paid INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, tournament_id)
);

CREATE TABLE IF NOT EXISTS achievements (
    id BIGSERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    emoji TEXT,
    tier TEXT DEFAULT 'easy',
    order_index INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS team_achievements (
    team_name TEXT NOT NULL,
    tournament_id BIGINT NOT NULL,
    achievement_id BIGINT NOT NULL REFERENCES achievements(id),
    PRIMARY KEY (team_name, tournament_id, achievement_id)
);

CREATE TABLE IF NOT EXISTS tournament_roster (
    tournament_id BIGINT NOT NULL,
    team_name TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    full_name TEXT,
    is_captain INTEGER DEFAULT 0,
    PRIMARY KEY (tournament_id, team_name, user_id)
);

CREATE TABLE IF NOT EXISTS player_achievements (
    tournament_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    achievement_id BIGINT NOT NULL,
    awarded_at TEXT DEFAULT CURRENT_TIMESTAMP,
    awarded_by BIGINT,
    note TEXT,
    PRIMARY KEY (tournament_id, user_id, achievement_id)
);

CREATE TABLE IF NOT EXISTS player_match_stats (
    tournament_id BIGINT NOT NULL,
    match_id BIGINT NOT NULL,
    team_name TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    points INTEGER DEFAULT 0,
    threes INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    rebounds INTEGER DEFAULT 0,
    steals INTEGER DEFAULT 0,
    blocks INTEGER DEFAULT 0,
    fouls INTEGER DEFAULT 0,
    turnovers INTEGER DEFAULT 0,
    minutes INTEGER DEFAULT 0,
    PRIMARY KEY (tournament_id, match_id, user_id)
);

CREATE TABLE IF NOT EXISTS player_stats (
    tournament_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    games INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    threes INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    rebounds INTEGER DEFAULT 0,
    steals INTEGER DEFAULT 0,
    blocks INTEGER DEFAULT 0,
    fouls INTEGER DEFAULT 0,
    turnovers INTEGER DEFAULT 0,
    minutes INTEGER DEFAULT 0,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tournament_id, user_id)
);

CREATE TABLE IF NOT EXISTS player_ratings (
    user_id BIGINT PRIMARY KEY,
    rating DOUBLE PRECISION DEFAULT 1000,
    games INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS player_ratings_by_tournament (
    tournament_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    rating DOUBLE PRECISION DEFAULT 1000,
    games INTEGER DEFAULT 0,
    PRIMARY KEY (tournament_id, user_id)
);

CREATE TABLE IF NOT EXISTS web_users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_teams_new_tournament ON teams_new(tournament_id);
CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_team_members_tourn ON team_members(tournament_id);
CREATE INDEX IF NOT EXISTS idx_free_agents_tourn ON free_agents_new(tournament_id);
CREATE INDEX IF NOT EXISTS idx_team_security_tourn ON team_security_new(tournament_id);
