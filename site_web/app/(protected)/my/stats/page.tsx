'use client';

import { useEffect, useState } from 'react';

import { useSession } from '@/components/session-provider';
import { ApiError, getMyStats } from '@/lib/api';

export default function MyStatsPage() {
  const { session, setSession } = useSession();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{
    aggregate: { games: number; wins: number; losses: number; points: number; assists: number; blocks: number };
    rating_global: { rating: number; games: number };
  } | null>(null);

  useEffect(() => {
    let mounted = true;

    async function run() {
      if (!session) return;
      setLoading(true);
      setError(null);
      try {
        const data = await getMyStats(session, (next) => setSession(next));
        if (!mounted) return;
        setStats(data);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError) setError(err.message);
        else setError('Не удалось загрузить статистику');
      } finally {
        if (mounted) setLoading(false);
      }
    }

    run();
    return () => {
      mounted = false;
    };
  }, [session, setSession]);

  return (
    <div className="reveal-up">
      <div className="section-head">
        <h2 className="section-title">Моя статистика</h2>
        <span className="tag">Аналитика игрока</span>
      </div>

      {loading ? <div className="notice">Загрузка статистики...</div> : null}
      {error ? <div className="notice error">{error}</div> : null}

      {stats ? (
        <>
          <section className="kpi-grid">
            <article className="metric">
              <p>Игры</p>
              <h3>{stats.aggregate.games || 0}</h3>
            </article>
            <article className="metric">
              <p>Победы</p>
              <h3>{stats.aggregate.wins || 0}</h3>
            </article>
            <article className="metric">
              <p>Поражения</p>
              <h3>{stats.aggregate.losses || 0}</h3>
            </article>
            <article className="metric">
              <p>Рейтинг</p>
              <h3>{Math.round(stats.rating_global.rating || 0)}</h3>
            </article>
          </section>

          <section className="card-grid">
            <article className="card">
              <h3>Очки</h3>
              <p>{stats.aggregate.points || 0}</p>
            </article>
            <article className="card">
              <h3>Передачи</h3>
              <p>{stats.aggregate.assists || 0}</p>
            </article>
            <article className="card">
              <h3>Блоки</h3>
              <p>{stats.aggregate.blocks || 0}</p>
            </article>
            <article className="card">
              <h3>Рейтинговые игры</h3>
              <p>{stats.rating_global.games || 0}</p>
            </article>
          </section>
        </>
      ) : null}
    </div>
  );
}
