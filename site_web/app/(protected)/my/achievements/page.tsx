'use client';

import { useEffect, useState } from 'react';

import { useSession } from '@/components/session-provider';
import { ApiError, getMyAchievements } from '@/lib/api';

export default function AchievementsPage() {
  const { session, setSession } = useSession();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<
    Array<{
      tournament_id: number;
      code: string;
      title: string;
      description: string;
      emoji: string;
      tier: string;
      awarded_at: string;
    }>
  >([]);

  useEffect(() => {
    let mounted = true;

    async function run() {
      if (!session) return;
      setLoading(true);
      setError(null);

      try {
        const data = await getMyAchievements(session, (next) => setSession(next));
        if (!mounted) return;
        setRows(data);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError) setError(err.message);
        else setError('Не удалось загрузить достижения');
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
        <h2 className="section-title">Достижения</h2>
        <span className="tag ok">Всего: {rows.length}</span>
      </div>

      {loading ? <div className="notice">Загрузка достижений...</div> : null}
      {error ? <div className="notice error">{error}</div> : null}

      <section className="card-grid">
        {rows.map((a) => (
          <article className="card" key={`${a.tournament_id}-${a.code}`}>
            <h3>
              {a.emoji || '🏆'} {a.title}
            </h3>
            <p>{a.description}</p>
            <p className="meta">
              код: {a.code} | уровень: {a.tier} | турнир: {a.tournament_id}
            </p>
          </article>
        ))}
      </section>
    </div>
  );
}
