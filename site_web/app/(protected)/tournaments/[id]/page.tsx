'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';

import { ApiError, getTournament, getTournamentInfo, getTournamentMatches, getTournamentStandings } from '@/lib/api';
import { statusLabelRu } from '@/lib/labels';

export default function TournamentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = useMemo(() => Number(params.id), [params.id]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [tournament, setTournament] = useState<{ id: number; name: string; date_start: string | null; venue: string | null; status: string } | null>(null);
  const [info, setInfo] = useState<Array<{ section: string; content: string | null }>>([]);
  const [standings, setStandings] = useState<Array<{ team_name: string; games: number; wins: number; losses: number; diff: number }>>([]);
  const [matches, setMatches] = useState<Array<{ id: number; stage: string | null; team_home_name: string; team_away_name: string; score_home: number | null; score_away: number | null; status: string }>>([]);

  useEffect(() => {
    let mounted = true;

    async function run() {
      setLoading(true);
      setError(null);

      try {
        const [tData, infoData, standingsData, matchesData] = await Promise.all([
          getTournament(id),
          getTournamentInfo(id),
          getTournamentStandings(id),
          getTournamentMatches(id),
        ]);
        if (!mounted) return;

        setTournament(tData);
        setInfo(infoData);
        setStandings(standingsData);
        setMatches(matchesData);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError) setError(err.message);
        else setError('Не удалось загрузить детали турнира');
      } finally {
        if (mounted) setLoading(false);
      }
    }

    if (!Number.isFinite(id)) {
      setError('Некорректный ID турнира');
      setLoading(false);
      return;
    }

    run();
    return () => {
      mounted = false;
    };
  }, [id]);

  return (
    <div className="reveal-up">
      <div className="section-head">
        <h2 className="section-title">Детали турнира</h2>
        {tournament ? <span className="tag">{statusLabelRu(tournament.status)}</span> : null}
      </div>

      {loading ? <div className="notice">Загрузка...</div> : null}
      {error ? <div className="notice error">{error}</div> : null}

      {tournament ? (
        <section className="card-grid">
          <article className="card">
            <h3>{tournament.name}</h3>
            <p>Дата: {tournament.date_start || 'уточняется'}</p>
            <p>Локация: {tournament.venue || 'уточняется'}</p>
          </article>
          <article className="card">
            <h3>Обзор</h3>
            <p>Разделов информации: {info.length}</p>
            <p>Матчей: {matches.length}</p>
            <p>Команд в таблице: {standings.length}</p>
          </article>
        </section>
      ) : null}

      <section className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>
              <th>Раздел</th>
              <th>Содержимое</th>
            </tr>
          </thead>
          <tbody>
            {info.map((row) => (
              <tr key={row.section}>
                <td>{row.section}</td>
                <td>{row.content || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
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
