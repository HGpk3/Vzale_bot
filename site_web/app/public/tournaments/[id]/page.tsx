'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';

import { ApiError, getTournament, getTournamentMatches, getTournamentStandings } from '@/lib/api';
import { statusLabelRu } from '@/lib/labels';

export default function PublicTournamentPage() {
  const params = useParams<{ id: string }>();
  const tournamentId = useMemo(() => Number(params.id), [params.id]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tournament, setTournament] = useState<{ id: number; name: string; date_start: string | null; venue: string | null; status: string } | null>(null);
  const [standings, setStandings] = useState<Array<{ team_name: string; games: number; wins: number; losses: number; diff: number }>>([]);
  const [matches, setMatches] = useState<Array<{ id: number; team_home_name: string; team_away_name: string; score_home: number | null; score_away: number | null; status: string }>>([]);

  useEffect(() => {
    let mounted = true;

    async function run() {
      setLoading(true);
      setError(null);
      try {
        const [t, s, m] = await Promise.all([
          getTournament(tournamentId),
          getTournamentStandings(tournamentId),
          getTournamentMatches(tournamentId),
        ]);
        if (!mounted) return;
        setTournament(t);
        setStandings(s);
        setMatches(m);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError) setError(err.message);
        else setError('Не удалось загрузить турнир');
      } finally {
        if (mounted) setLoading(false);
      }
    }

    if (!Number.isFinite(tournamentId)) {
      setError('Некорректный ID турнира');
      setLoading(false);
      return;
    }

    run();
    return () => {
      mounted = false;
    };
  }, [tournamentId]);

  return (
    <div className="page-wrap reveal-up">
      <section className="hero-phone">
        <span className="tag">Публичный просмотр</span>
        <h1 className="hero-title">
          Турнир <strong>VZALE</strong>
        </h1>
        {loading ? <p className="hero-subtitle">Загрузка...</p> : null}
        {error ? <div className="notice error">{error}</div> : null}

        {tournament ? (
          <div className="card-grid">
            <article className="card">
              <h3>{tournament.name}</h3>
              <p>Дата: {tournament.date_start || 'уточняется'}</p>
              <p>Локация: {tournament.venue || 'уточняется'}</p>
              <p className="meta">Статус: {statusLabelRu(tournament.status)}</p>
            </article>
            <article className="card">
              <h3>Матчи</h3>
              <p>Доступно матчей: {matches.length}</p>
              <p className="meta">Команд в таблице: {standings.length}</p>
            </article>
          </div>
        ) : null}
      </section>

      <section className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>
              <th>Команда</th>
              <th>И</th>
              <th>В</th>
              <th>П</th>
              <th>Разница</th>
            </tr>
          </thead>
          <tbody>
            {standings.map((row) => (
              <tr key={row.team_name}>
                <td>{row.team_name}</td>
                <td>{row.games}</td>
                <td>{row.wins}</td>
                <td>{row.losses}</td>
                <td>{row.diff}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
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
