import type { Session } from '@/lib/session';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8100';

type ApiEnvelope<T> = {
  ok: boolean;
  data: T;
  meta?: Record<string, unknown>;
  error?: { detail?: string };
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function parseJson<T>(response: Response): Promise<ApiEnvelope<T> | null> {
  try {
    return (await response.json()) as ApiEnvelope<T>;
  } catch {
    return null;
  }
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (!headers.get('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: 'no-store',
  });

  const json = await parseJson<T>(response);

  if (!response.ok || !json?.ok) {
    const detail = json?.error?.detail || json?.data || response.statusText || 'Ошибка запроса';
    throw new ApiError(String(detail), response.status);
  }

  return json.data;
}

export async function login(username: string, password: string) {
  return request<{
    access_token: string;
    refresh_token: string;
    token_type: string;
    user_id: number;
    is_admin: boolean;
  }>('/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export async function refreshToken(refresh: string) {
  return request<{ access_token: string; refresh_token: string; token_type: string }>('/v1/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refresh }),
  });
}

export async function startBotLoginSession() {
  return request<{
    session_id: string;
    code: string;
    expires_at: string;
    expires_in_seconds: number;
  }>('/v1/auth/bot-login/start', {
    method: 'POST',
  });
}

export async function getBotLoginSessionStatus(sessionId: string) {
  return request<{
    session_id: string;
    status: 'pending' | 'approved' | 'expired' | 'consumed';
    approved: boolean;
    expired: boolean;
    consumed: boolean;
    telegram_id: number | null;
    full_name: string | null;
    username: string | null;
    approved_at: string | null;
    expires_at: string | null;
  }>(`/v1/auth/bot-login/status/${sessionId}`);
}

export async function finishBotLoginSession(sessionId: string) {
  return request<{
    access_token: string;
    refresh_token: string;
    token_type: string;
    user_id: number;
    is_admin: boolean;
  }>('/v1/auth/bot-login/finish', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function authedRequest<T>(
  session: Session,
  updateSession: (next: Session) => void,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await request<T>(path, init, session.accessToken);
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 401) {
      throw err;
    }

    const refreshed = await refreshToken(session.refreshToken);
    const nextSession: Session = {
      ...session,
      accessToken: refreshed.access_token,
      refreshToken: refreshed.refresh_token,
    };
    updateSession(nextSession);

    return request<T>(path, init, nextSession.accessToken);
  }
}

export async function getMe(session: Session, updateSession: (next: Session) => void) {
  return authedRequest<{ user_id: number; full_name: string | null; team: string | null; current_tournament_id: number | null }>(
    session,
    updateSession,
    '/v1/me',
  );
}

export async function updateMe(
  session: Session,
  updateSessionFn: (next: Session) => void,
  payload: { full_name?: string | null; current_tournament_id?: number | null },
) {
  return authedRequest(session, updateSessionFn, '/v1/me', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function getMyTeams(session: Session, updateSessionFn: (next: Session) => void) {
  return authedRequest<Array<{ team_name: string }>>(session, updateSessionFn, '/v1/me/teams');
}

export async function getMyAchievements(session: Session, updateSessionFn: (next: Session) => void) {
  return authedRequest<
    Array<{
      tournament_id: number;
      code: string;
      title: string;
      description: string;
      emoji: string;
      tier: string;
      awarded_at: string;
    }>
  >(session, updateSessionFn, '/v1/me/achievements?limit=200&offset=0');
}

export async function getMyStats(session: Session, updateSessionFn: (next: Session) => void) {
  return authedRequest<{
    aggregate: {
      games: number;
      wins: number;
      losses: number;
      points: number;
      assists: number;
      blocks: number;
    };
    rating_global: { rating: number; games: number };
  }>(session, updateSessionFn, '/v1/me/stats');
}

export async function listTournaments(status: 'active' | 'archived' | 'all' = 'active') {
  return request<Array<{ id: number; name: string; date_start: string | null; venue: string | null; status: string }>>(
    `/v1/tournaments?status=${status}&limit=200&offset=0`,
  );
}

export async function getTournament(id: number) {
  return request<{ id: number; name: string; date_start: string | null; venue: string | null; status: string }>(
    `/v1/tournaments/${id}`,
  );
}

export async function getTournamentInfo(id: number) {
  return request<Array<{ section: string; content: string | null; updated_at: string | null }>>(
    `/v1/tournaments/${id}/info`,
  );
}

export async function getTournamentStandings(id: number) {
  return request<
    Array<{
      team_name: string;
      games: number;
      wins: number;
      losses: number;
      points_for: number;
      points_against: number;
      diff: number;
    }>
  >(`/v1/tournaments/${id}/standings`);
}

export async function getTournamentMatches(id: number) {
  return request<
    Array<{
      id: number;
      stage: string | null;
      team_home_name: string;
      team_away_name: string;
      score_home: number | null;
      score_away: number | null;
      status: string;
    }>
  >(`/v1/tournaments/${id}/matches?limit=300&offset=0`);
}

export async function getTeam(session: Session, updateSessionFn: (next: Session) => void, teamName: string) {
  return authedRequest<{
    team_name: string;
    invite_code: string | null;
    members: Array<{ member_id: number; member_name: string }>;
  }>(session, updateSessionFn, `/v1/teams/${encodeURIComponent(teamName)}`);
}

export async function createTeam(
  session: Session,
  updateSessionFn: (next: Session) => void,
  payload: { team_name: string; tournament_id?: number | null; full_name?: string | null },
) {
  return authedRequest<{ team_name: string; invite_code: string }>(session, updateSessionFn, '/v1/teams', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function joinTeamByCode(
  session: Session,
  updateSessionFn: (next: Session) => void,
  payload: { invite_code: string; tournament_id?: number | null; full_name?: string | null },
) {
  return authedRequest<{ team_name: string }>(session, updateSessionFn, '/v1/teams/join-by-code', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function leaveTeam(
  session: Session,
  updateSessionFn: (next: Session) => void,
  teamName: string,
) {
  return authedRequest<{ left: boolean }>(
    session,
    updateSessionFn,
    `/v1/teams/${encodeURIComponent(teamName)}/leave`,
    { method: 'POST' },
  );
}

export async function regenerateInvite(
  session: Session,
  updateSessionFn: (next: Session) => void,
  teamName: string,
) {
  return authedRequest<{ team_name: string; invite_code: string }>(
    session,
    updateSessionFn,
    `/v1/teams/${encodeURIComponent(teamName)}/invite-code/regenerate`,
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
  );
}

export async function createTournamentAdmin(
  session: Session,
  updateSessionFn: (next: Session) => void,
  payload: { name: string; status?: string; date_start?: string | null; venue?: string | null },
) {
  return authedRequest<{ tournament_id: number }>(session, updateSessionFn, '/v1/admin/tournaments', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function patchTournamentAdmin(
  session: Session,
  updateSessionFn: (next: Session) => void,
  tournamentId: number,
  payload: { name?: string; date_start?: string | null; venue?: string | null },
) {
  return authedRequest<{ updated: number }>(
    session,
    updateSessionFn,
    `/v1/admin/tournaments/${tournamentId}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
  );
}

export async function setTournamentStatusAdmin(
  session: Session,
  updateSessionFn: (next: Session) => void,
  tournamentId: number,
  status: string,
) {
  return authedRequest<{ status: string }>(
    session,
    updateSessionFn,
    `/v1/admin/tournaments/${tournamentId}/status`,
    { method: 'POST', body: JSON.stringify({ status }) },
  );
}

export async function createMatchAdmin(
  session: Session,
  updateSessionFn: (next: Session) => void,
  tournamentId: number,
  payload: { stage?: string | null; team_home_name: string; team_away_name: string },
) {
  return authedRequest<{ match_id: number }>(
    session,
    updateSessionFn,
    `/v1/admin/tournaments/${tournamentId}/matches`,
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export async function listSuggestionsAdmin(session: Session, updateSessionFn: (next: Session) => void) {
  return authedRequest<
    Array<{ id: number; user_id: number; text: string; status: string; created_at: string; tournament_id: number | null }>
  >(session, updateSessionFn, '/v1/admin/suggestions?limit=200&offset=0');
}

export async function replySuggestionAdmin(
  session: Session,
  updateSessionFn: (next: Session) => void,
  suggestionId: number,
  replyText: string,
) {
  return authedRequest<{ suggestion_id: number; reply_text: string }>(
    session,
    updateSessionFn,
    `/v1/admin/suggestions/${suggestionId}/reply`,
    {
      method: 'POST',
      body: JSON.stringify({ reply_text: replyText }),
    },
  );
}
