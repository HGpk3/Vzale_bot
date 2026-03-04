'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ApiError, listTournaments } from '@/lib/api';
import { statusLabelRu } from '@/lib/labels';

export default function TournamentsPage() {
  const [status, setStatus] = useState<'active' | 'archived' | 'all'>('active');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Array<{ id: number; name: string; status: string; date_start: string | null; venue: string | null }>>([]);

  useEffect(() => {
    let mounted = true;
    async function run() {
      setLoading(true);
      setError(null);
      try {
        const data = await listTournaments(status);
        if (!mounted) return;
        setRows(data);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError) setError(err.message);
        else setError('Не удалось загрузить турниры');
      } finally {
        if (mounted) setLoading(false);
      }
    }

    run();
    return () => {
      mounted = false;
    };
  }, [status]);

  return (
    <div className="reveal-up">
      <div className="section-head">
        <h2 className="section-title">Турниры</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className={status === 'active' ? 'btn primary' : 'btn ghost'} onClick={() => setStatus('active')}>
            Активные
          </button>
          <button className={status === 'archived' ? 'btn primary' : 'btn ghost'} onClick={() => setStatus('archived')}>
            Архив
          </button>
          <button className={status === 'all' ? 'btn primary' : 'btn ghost'} onClick={() => setStatus('all')}>
            Все
          </button>
        </div>
      </div>

      {loading ? <div className="notice">Загрузка...</div> : null}
      {error ? <div className="notice error">{error}</div> : null}

      <section className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Статус</th>
              <th>Дата</th>
              <th>Локация</th>
              <th>Открыть</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td>{row.name}</td>
                <td>{statusLabelRu(row.status)}</td>
                <td>{row.date_start || '-'}</td>
                <td>{row.venue || '-'}</td>
                <td>
                  <Link href={`/tournaments/${row.id}`}>Подробнее</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
