'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { useSession } from '@/components/session-provider';
import { ApiError, getMe, listTournaments } from '@/lib/api';
import { statusLabelRu } from '@/lib/labels';

export default function DashboardPage() {
  const { session, setSession } = useSession();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [me, setMe] = useState<{ user_id: number; full_name: string | null; team: string | null; current_tournament_id: number | null } | null>(null);
  const [tournaments, setTournaments] = useState<Array<{ id: number; name: string; status: string }>>([]);

  useEffect(() => {
    let mounted = true;

    async function run() {
      if (!session) return;
      setLoading(true);
      setError(null);

      try {
        const [meData, activeTournaments] = await Promise.all([
          getMe(session, (next) => setSession(next)),
          listTournaments('active'),
        ]);
        if (!mounted) return;
        setMe(meData);
        setTournaments(activeTournaments);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError) setError(err.message);
        else setError('Не удалось загрузить дашборд');
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
        <h2 className="section-title">Дашборд</h2>
        <span className="tag ok">API онлайн</span>
      </div>

      {loading ? <div className="notice">Загрузка дашборда...</div> : null}
      {error ? <div className="notice error">{error}</div> : null}

      <section className="kpi-grid">
        <article className="metric">
          <p>Пользователь</p>
          <h3>{me?.full_name || `#${me?.user_id || session?.userId}`}</h3>
        </article>
        <article className="metric">
          <p>Текущая команда</p>
          <h3>{me?.team || 'НЕТ'}</h3>
        </article>
        <article className="metric">
          <p>Активные турниры</p>
          <h3>{tournaments.length}</h3>
        </article>
        <article className="metric">
          <p>Роль</p>
          <h3>{session?.isAdmin ? 'АДМИН' : 'ИГРОК'}</h3>
        </article>
      </section>

      <section className="card-grid">
        <article className="card">
          <h3>Быстрый доступ</h3>
          <p>Открыть турнирный модуль и посмотреть матчи/таблицу.</p>
          <p className="meta">
            <Link href="/tournaments">Перейти к турнирам</Link>
          </p>
        </article>
        <article className="card">
          <h3>Центр команды</h3>
          <p>Создать команду, вступить по коду, обновить инвайт для новых игроков.</p>
          <p className="meta">
            <Link href="/my/team">Открыть управление командой</Link>
          </p>
        </article>
      </section>

      <section className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Статус</th>
              <th>Действие</th>
            </tr>
          </thead>
          <tbody>
            {tournaments.map((t) => (
              <tr key={t.id}>
                <td>{t.id}</td>
                <td>{t.name}</td>
                <td>{statusLabelRu(t.status)}</td>
                <td>
                  <Link href={`/tournaments/${t.id}`}>Открыть</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
