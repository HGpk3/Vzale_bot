'use client';

import { FormEvent, useEffect, useState } from 'react';

import { useSession } from '@/components/session-provider';
import {
  ApiError,
  createTeam,
  getMe,
  getMyTeams,
  getTeam,
  joinTeamByCode,
  leaveTeam,
  regenerateInvite,
} from '@/lib/api';
import { getStoredSession } from '@/lib/session';

export default function TeamPage() {
  const { session, setSession } = useSession();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [myTeam, setMyTeam] = useState<string | null>(null);
  const [myTeams, setMyTeams] = useState<Array<{ team_name: string }>>([]);
  const [teamDetails, setTeamDetails] = useState<{
    team_name: string;
    invite_code: string | null;
    members: Array<{ member_id: number; member_name: string }>;
  } | null>(null);

  const [createName, setCreateName] = useState('');
  const [createTournamentId, setCreateTournamentId] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [fullName, setFullName] = useState('');

  async function refreshState(preferredTeam?: string | null) {
    if (!session) return;

    const s1 = getStoredSession() || session;
    const me = await getMe(s1, (next) => setSession(next));
    const s2 = getStoredSession() || s1;
    const teams = await getMyTeams(s2, (next) => setSession(next));

    const teamName = preferredTeam || me.team || teams[0]?.team_name || null;
    setMyTeam(me.team || null);
    setMyTeams(teams);

    if (teamName) {
      const s3 = getStoredSession() || s2;
      const detail = await getTeam(s3, (next) => setSession(next), teamName);
      setTeamDetails(detail);
      return;
    }

    setTeamDetails(null);
  }

  useEffect(() => {
    let mounted = true;
    async function run() {
      if (!session) return;
      setLoading(true);
      setError(null);
      try {
        await refreshState();
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError) setError(err.message);
        else setError('Не удалось загрузить раздел команды');
      } finally {
        if (mounted) setLoading(false);
      }
    }

    run();
    return () => {
      mounted = false;
    };
  }, [session]);

  async function onCreateTeam(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setError(null);
    setNotice(null);

    try {
      const result = await createTeam(session, (next) => setSession(next), {
        team_name: createName,
        tournament_id: createTournamentId ? Number(createTournamentId) : undefined,
        full_name: fullName || undefined,
      });
      await refreshState(result.team_name);
      setCreateName('');
      setCreateTournamentId('');
      setNotice(`Команда создана. Код приглашения: ${result.invite_code}`);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError('Не удалось создать команду');
    }
  }

  async function onJoinByCode(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setError(null);
    setNotice(null);

    try {
      const result = await joinTeamByCode(session, (next) => setSession(next), {
        invite_code: joinCode,
        full_name: fullName || undefined,
      });
      await refreshState(result.team_name);
      setJoinCode('');
      setNotice(`Вы вступили в команду ${result.team_name}`);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError('Не удалось вступить по коду');
    }
  }

  async function onLeaveTeam() {
    if (!session || !teamDetails) return;
    setError(null);

    try {
      await leaveTeam(session, (next) => setSession(next), teamDetails.team_name);
      await refreshState(null);
      setNotice('Вы вышли из команды');
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError('Не удалось выйти из команды');
    }
  }

  async function onRegenerateCode() {
    if (!session || !teamDetails) return;
    setError(null);

    try {
      const result = await regenerateInvite(session, (next) => setSession(next), teamDetails.team_name);
      setNotice(`Новый код: ${result.invite_code}`);
      await refreshState(teamDetails.team_name);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError('Не удалось обновить инвайт-код');
    }
  }

  return (
    <div className="reveal-up">
      <div className="section-head">
        <h2 className="section-title">Моя команда</h2>
        <span className="tag">Управление командой</span>
      </div>

      {loading ? <div className="notice">Загрузка раздела команды...</div> : null}
      {error ? <div className="notice error">{error}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <div className="split">
        <form className="form-panel" onSubmit={onCreateTeam}>
          <h3>Создать команду</h3>
          <label>
            Название команды
            <input value={createName} onChange={(e) => setCreateName(e.target.value)} required />
          </label>
          <label>
            Ваше имя и фамилия
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Необязательно" />
          </label>
          <label>
            ID турнира
            <input value={createTournamentId} onChange={(e) => setCreateTournamentId(e.target.value)} placeholder="Необязательно" />
          </label>
          <button className="btn primary" type="submit">
            Создать
          </button>
        </form>

        <form className="form-panel" onSubmit={onJoinByCode}>
          <h3>Вступить по коду</h3>
          <label>
            Инвайт-код
            <input value={joinCode} onChange={(e) => setJoinCode(e.target.value)} required />
          </label>
          <button className="btn" type="submit">
            Вступить
          </button>
        </form>
      </div>

      <section className="card-grid">
        <article className="card">
          <h3>Текущая команда</h3>
          <p>{myTeam || 'Команда не выбрана'}</p>
          {teamDetails ? (
            <div className="hero-actions">
              <button className="btn warn" onClick={onRegenerateCode}>
                Обновить инвайт
              </button>
              <button className="btn danger" onClick={onLeaveTeam}>
                Выйти из команды
              </button>
            </div>
          ) : null}
        </article>

        <article className="card">
          <h3>Список моих команд</h3>
          <p>{myTeams.map((t) => t.team_name).join(', ') || 'Пусто'}</p>
          <p className="meta">Инвайт: {teamDetails?.invite_code || '-'}</p>
        </article>
      </section>

      <section className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>
              <th>ID участника</th>
              <th>Имя</th>
            </tr>
          </thead>
          <tbody>
            {(teamDetails?.members || []).map((member) => (
              <tr key={member.member_id}>
                <td>{member.member_id}</td>
                <td>{member.member_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
