'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';

import { useSession } from '@/components/session-provider';
import {
  ApiError,
  createMatchAdmin,
  getTournament,
  getTournamentMatches,
  patchTournamentAdmin,
  setTournamentStatusAdmin,
} from '@/lib/api';
import { statusLabelRu } from '@/lib/labels';

export default function AdminTournamentPage() {
  const params = useParams<{ id: string }>();
  const id = useMemo(() => Number(params.id), [params.id]);

  const { session, setSession } = useSession();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [tournament, setTournament] = useState<{ id: number; name: string; date_start: string | null; venue: string | null; status: string } | null>(null);
  const [matches, setMatches] = useState<
    Array<{ id: number; stage: string | null; team_home_name: string; team_away_name: string; score_home: number | null; score_away: number | null; status: string }>
  >([]);

  const [patchName, setPatchName] = useState('');
  const [patchDate, setPatchDate] = useState('');
  const [patchVenue, setPatchVenue] = useState('');

  const [stage, setStage] = useState('group');
  const [homeTeam, setHomeTeam] = useState('');
  const [awayTeam, setAwayTeam] = useState('');

  async function refreshData() {
    const [t, m] = await Promise.all([getTournament(id), getTournamentMatches(id)]);
    setTournament(t);
    setMatches(m);
    setPatchName(t.name || '');
    setPatchDate(t.date_start || '');
    setPatchVenue(t.venue || '');
  }

  useEffect(() => {
    let mounted = true;

    async function run() {
      if (!session?.isAdmin) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        await refreshData();
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError) setError(err.message);
        else setError('Не удалось загрузить страницу управления турниром');
      } finally {
        if (mounted) setLoading(false);
      }
    }

    run();
    return () => {
      mounted = false;
    };
  }, [session, id]);

  async function onPatch(e: FormEvent) {
    e.preventDefault();
    if (!session) return;

    setError(null);
    setNotice(null);

    try {
      await patchTournamentAdmin(session, (next) => setSession(next), id, {
        name: patchName,
        date_start: patchDate || null,
        venue: patchVenue || null,
      });
      await refreshData();
      setNotice('Турнир обновлен');
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError('Не удалось обновить турнир');
    }
  }

  async function onStatusChange(nextStatus: string) {
    if (!session) return;

    setError(null);
    setNotice(null);

    try {
      await setTournamentStatusAdmin(session, (next) => setSession(next), id, nextStatus);
      await refreshData();
      setNotice(`Статус обновлен: ${statusLabelRu(nextStatus)}`);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError('Не удалось изменить статус');
    }
  }

  async function onCreateMatch(e: FormEvent) {
    e.preventDefault();
    if (!session) return;

    setError(null);
    setNotice(null);

    try {
      await createMatchAdmin(session, (next) => setSession(next), id, {
        stage,
        team_home_name: homeTeam,
        team_away_name: awayTeam,
      });
      setHomeTeam('');
      setAwayTeam('');
      await refreshData();
      setNotice('Матч создан');
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError('Не удалось создать матч');
    }
  }

  if (!session?.isAdmin) {
    return <div className="notice error">Нужны права администратора.</div>;
  }

  return (
    <div className="reveal-up">
      <div className="section-head">
        <h2 className="section-title">Управление турниром #{id}</h2>
        {tournament ? <span className="tag warn">{statusLabelRu(tournament.status)}</span> : null}
      </div>

      {loading ? <div className="notice">Загрузка...</div> : null}
      {error ? <div className="notice error">{error}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <div className="split">
        <form className="form-panel" onSubmit={onPatch}>
          <h3>Редактировать турнир</h3>
          <label>
            Название
            <input value={patchName} onChange={(e) => setPatchName(e.target.value)} />
          </label>
          <label>
            Дата
            <input value={patchDate} onChange={(e) => setPatchDate(e.target.value)} placeholder="YYYY-MM-DD" />
          </label>
          <label>
            Локация
            <input value={patchVenue} onChange={(e) => setPatchVenue(e.target.value)} />
          </label>
          <button className="btn primary" type="submit">
            Сохранить
          </button>

          <div className="hero-actions">
            <button type="button" className="btn" onClick={() => onStatusChange('announced')}>
              announced
            </button>
            <button type="button" className="btn" onClick={() => onStatusChange('registration_open')}>
              registration_open
            </button>
            <button type="button" className="btn" onClick={() => onStatusChange('running')}>
              running
            </button>
            <button type="button" className="btn danger" onClick={() => onStatusChange('archived')}>
              archived
            </button>
          </div>
        </form>

        <form className="form-panel" onSubmit={onCreateMatch}>
          <h3>Создать матч</h3>
          <label>
            Этап
            <input value={stage} onChange={(e) => setStage(e.target.value)} />
          </label>
          <label>
            Команда хозяев
            <input value={homeTeam} onChange={(e) => setHomeTeam(e.target.value)} required />
          </label>
          <label>
            Команда гостей
            <input value={awayTeam} onChange={(e) => setAwayTeam(e.target.value)} required />
          </label>
          <button className="btn primary" type="submit">
            Добавить матч
          </button>
        </form>
      </div>

      <section className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Этап</th>
              <th>Хозяева</th>
              <th>Гости</th>
              <th>Счет</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.id}>
                <td>{m.id}</td>
                <td>{m.stage || '-'}</td>
                <td>{m.team_home_name}</td>
                <td>{m.team_away_name}</td>
                <td>
                  {m.score_home ?? '-'} : {m.score_away ?? '-'}
                </td>
                <td>{statusLabelRu(m.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
