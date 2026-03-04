'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { ApiError, listTournaments } from '@/lib/api';
import { statusLabelRu } from '@/lib/labels';

export default function PublicTournamentsListPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Array<{ id: number; name: string; status: string; date_start: string | null; venue: string | null }>>([]);

  useEffect(() => {
    let mounted = true;

    async function run() {
      setLoading(true);
      setError(null);
      try {
        const data = await listTournaments('active');
        if (!mounted) return;
        setRows(data);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError('Не удалось загрузить список турниров');
        }
      } finally {
        if (mounted) setLoading(false);
      }
    }

    run();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="page-wrap reveal-up">
      <section className="hero-phone">
        <span className="hero-kicker">VZALE / Публичный раздел</span>
        <h1 className="hero-title">
          Предстоящие <strong>Турниры</strong>
        </h1>
        <p className="hero-subtitle">
          Публичная витрина активных турниров VZALE. Выберите турнир и откройте детали: матчи, таблица и текущий
          статус.
        </p>
      </section>

      {loading ? <div className="notice" style={{ marginTop: 14 }}>Загрузка...</div> : null}
      {error ? <div className="notice error" style={{ marginTop: 14 }}>{error}</div> : null}

      <section className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Статус</th>
              <th>Дата</th>
              <th>Локация</th>
              <th>Подробнее</th>
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
                  <Link href={`/public/tournaments/${row.id}`}>Открыть</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
