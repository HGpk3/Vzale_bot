-- 01_init_multitournament.sql
-- ⚠️ Перед запуском сделайте бэкап:
-- cp tournament.db tournament.backup.$(date +%Y%m%d_%H%M%S).db

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- 1) Таблица турниров
CREATE TABLE IF NOT EXISTS tournaments (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,
  date_start      TEXT,
  venue           TEXT,
  status          TEXT DEFAULT 'draft', -- draft|announced|registration_open|closed|running|finished|archived
  settings_json   TEXT,
  lock_rosters_at TEXT,
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Создадим Турнир №1, если нет
INSERT INTO tournaments (name, status)
SELECT 'Турнир №1', 'running'
WHERE NOT EXISTS (SELECT 1 FROM tournaments);

-- 2) Новая таблица команд
CREATE TABLE IF NOT EXISTS teams_new (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  tournament_id    INTEGER NOT NULL,
  name             TEXT NOT NULL,
  captain_user_id  INTEGER,
  status           TEXT DEFAULT 'active',
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
);

-- 3) Участники команд
CREATE TABLE IF NOT EXISTS team_members (
  team_id         INTEGER NOT NULL,
  user_id         INTEGER NOT NULL,
  role            TEXT DEFAULT 'player',   -- captain|player
  status          TEXT DEFAULT 'confirmed',-- pending|confirmed
  tournament_id   INTEGER NOT NULL,
  PRIMARY KEY (team_id, user_id),
  FOREIGN KEY (team_id) REFERENCES teams_new(id) ON DELETE CASCADE,
  FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
);

-- 4) Свободные игроки
CREATE TABLE IF NOT EXISTS free_agents_new (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL,
  tournament_id INTEGER NOT NULL,
  profile_json  TEXT,
  is_active     INTEGER DEFAULT 1,
  FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
);

-- 5) Инвайт-коды для команд
CREATE TABLE IF NOT EXISTS team_security_new (
  tournament_id INTEGER NOT NULL,
  team_id       INTEGER NOT NULL,
  invite_code   TEXT NOT NULL UNIQUE,
  PRIMARY KEY (tournament_id, team_id),
  FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE,
  FOREIGN KEY (team_id)       REFERENCES teams_new(id)   ON DELETE CASCADE
);

-- 6) Информация о турнире
CREATE TABLE IF NOT EXISTS tournament_info (
  tournament_id INTEGER NOT NULL,
  section       TEXT NOT NULL,  -- about|rules|schedule|brackets|map|contacts|faq
  content       TEXT,
  updated_at    TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tournament_id, section),
  FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
);

-- 7) Матчи и таблица результатов
CREATE TABLE IF NOT EXISTS matches (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  tournament_id INTEGER NOT NULL,
  stage         TEXT,
  group_name    TEXT,
  round         TEXT,
  court         TEXT,
  start_at      TEXT,
  team_home_id  INTEGER NOT NULL,
  team_away_id  INTEGER NOT NULL,
  score_home    INTEGER,
  score_away    INTEGER,
  status        TEXT DEFAULT 'scheduled', -- scheduled|finished|wo
  FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE,
  FOREIGN KEY (team_home_id)  REFERENCES teams_new(id)   ON DELETE CASCADE,
  FOREIGN KEY (team_away_id)  REFERENCES teams_new(id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS standings (
  tournament_id   INTEGER NOT NULL,
  team_id         INTEGER NOT NULL,
  wins            INTEGER DEFAULT 0,
  losses          INTEGER DEFAULT 0,
  points_for      INTEGER DEFAULT 0,
  points_against  INTEGER DEFAULT 0,
  diff            INTEGER DEFAULT 0,
  win_pct         REAL    DEFAULT 0,
  PRIMARY KEY (tournament_id, team_id),
  FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE,
  FOREIGN KEY (team_id)       REFERENCES teams_new(id)   ON DELETE CASCADE
);

-- 8) Добавляем tournament_id в коммуникации
ALTER TABLE polls_group ADD COLUMN tournament_id INTEGER;
ALTER TABLE polls       ADD COLUMN tournament_id INTEGER;
ALTER TABLE suggestions ADD COLUMN tournament_id INTEGER;

-- 9) Перенос данных из старых таблиц
WITH old_teams AS (
  SELECT team_name,
         MIN(member_id) AS captain_user_id
  FROM   teams
  GROUP  BY team_name
)
INSERT INTO teams_new (tournament_id, name, captain_user_id, status)
SELECT (SELECT id FROM tournaments LIMIT 1),
       ot.team_name,
       ot.captain_user_id,
       'active'
FROM old_teams ot
WHERE ot.team_name IS NOT NULL;

INSERT OR IGNORE INTO team_members (team_id, user_id, role, status, tournament_id)
SELECT t.id, legacy.member_id,
       CASE WHEN legacy.member_id = t.captain_user_id THEN 'captain' ELSE 'player' END,
       'confirmed',
       t.tournament_id
FROM teams AS legacy
JOIN teams_new t
  ON t.name = legacy.team_name
WHERE legacy.team_name IS NOT NULL
  AND legacy.member_id IS NOT NULL;

INSERT INTO free_agents_new (user_id, tournament_id, profile_json, is_active)
SELECT fa.user_id,
       (SELECT id FROM tournaments LIMIT 1),
       json_object('name', COALESCE(fa.name,''), 'info', COALESCE(fa.info,'')),
       1
FROM free_agents fa;

INSERT OR IGNORE INTO team_security_new (tournament_id, team_id, invite_code)
SELECT (SELECT id FROM tournaments LIMIT 1),
       tn.id,
       ts.invite_code
FROM team_security ts
JOIN teams_new tn ON tn.name = ts.team_name
WHERE ts.invite_code IS NOT NULL AND ts.invite_code <> '';

UPDATE polls_group SET tournament_id = (SELECT id FROM tournaments LIMIT 1) WHERE tournament_id IS NULL;
UPDATE polls       SET tournament_id = (SELECT id FROM tournaments LIMIT 1) WHERE tournament_id IS NULL;
UPDATE suggestions SET tournament_id = (SELECT id FROM tournaments LIMIT 1) WHERE tournament_id IS NULL;

-- 10) Индексы
CREATE INDEX IF NOT EXISTS idx_teams_new_tournament ON teams_new(tournament_id);
CREATE INDEX IF NOT EXISTS idx_team_members_team     ON team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_team_members_tourn    ON team_members(tournament_id);
CREATE INDEX IF NOT EXISTS idx_free_agents_tourn     ON free_agents_new(tournament_id);
CREATE INDEX IF NOT EXISTS idx_team_security_tourn   ON team_security_new(tournament_id);

COMMIT;
PRAGMA foreign_keys = ON;

-- После проверки:
-- ALTER TABLE teams RENAME TO teams_old;
-- ALTER TABLE teams_new RENAME TO teams;
-- ALTER TABLE free_agents RENAME TO free_agents_old;
-- ALTER TABLE free_agents_new RENAME TO free_agents;
-- ALTER TABLE team_security RENAME TO team_security_old;
-- ALTER TABLE team_security_new RENAME TO team_security;
