'use client';

import Link from 'next/link';
import { FormEvent, useEffect, useState } from 'react';

import { useSession } from '@/components/session-provider';
import {
  ApiError,
  createTournamentAdmin,
  listSuggestionsAdmin,
  listTournaments,
  replySuggestionAdmin,
} from '@/lib/api';
import { statusLabelRu } from '@/lib/labels';

export default function AdminPage() {
  const { session, setSession } = useSession();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [status, setStatus] = useState('draft');
  const [dateStart, setDateStart] = useState('');
  const [venue, setVenue] = useState('');

  const [tournaments, setTournaments] = useState<Array<{ id: number; name: string; status: string }>>([]);
  const [suggestions, setSuggestions] = useState<Array<{ id: number; user_id: number; text: string; status: string }>>([]);
  const [replyMap, setReplyMap] = useState<Record<number, string>>({});

  async function refreshData() {
    if (!session) return;
    const [t, s] = await Promise.all([
      listTournaments('all'),
      listSuggestionsAdmin(session, (next) => setSession(next)),
    ]);
    setTournaments(t);
    setSuggestions(s);
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
        else setError('Не удалось загрузить админ-модуль');
      } finally {
        if (mounted) setLoading(false);
      }
    }

    run();
    return () => {
      mounted = false;
    };
  }, [session]);

  async function onCreateTournament(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setError(null);
    setNotice(null);

    try {
      const created = await createTournamentAdmin(session, (next) => setSession(next), {
        name,
        status,
        date_start: dateStart || null,
        venue: venue || null,
      });
      setNotice(`Турнир создан: #${created.tournament_id}`);
      setName('');
      setDateStart('');
      setVenue('');
      await refreshData();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError('Не удалось создать турнир');
    }
  }

  async function onReply(id: number) {
    if (!session) return;
    const reply = (replyMap[id] || '').trim();
    if (!reply) return;

    setError(null);
    setNotice(null);

    try {
      await replySuggestionAdmin(session, (next) => setSession(next), id, reply);
      setReplyMap((prev) => ({ ...prev, [id]: '' }));
      setNotice(`Ответ на предложение #${id} отправлен`);
      await refreshData();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError('Не удалось отправить ответ');
    }
  }

  if (!session?.isAdmin) {
    return <div className="notice error">Нужны права администратора.</div>;
  }

  return (
    <div className="reveal-up">
      <div className="section-head">
        <h2 className="section-title">Админ-консоль</h2>
        <span className="tag warn">Закрытый раздел</span>
      </div>

      {loading ? <div className="notice">Загрузка данных админки...</div> : null}
      {error ? <div className="notice error">{error}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <div className="split">
        <form className="form-panel" onSubmit={onCreateTournament}>
          <h3>Создать турнир</h3>
          <label>
            Название
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Статус
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="draft">Черновик</option>
              <option value="announced">Анонсирован</option>
              <option value="registration_open">Открыта регистрация</option>
              <option value="running">Идет</option>
              <option value="archived">Архив</option>
            </select>
          </label>
          <label>
            Дата
            <input value={dateStart} onChange={(e) => setDateStart(e.target.value)} placeholder="YYYY-MM-DD" />
          </label>
          <label>
            Локация
            <input value={venue} onChange={(e) => setVenue(e.target.value)} />
          </label>
          <button className="btn primary" type="submit">
            Создать
          </button>
        </form>

        <section className="form-panel">
          <h3>Турниры</h3>
          {tournaments.map((t) => (
            <div key={t.id} className="card" style={{ padding: 12 }}>
              <strong>{t.name}</strong>
              <p>Статус: {statusLabelRu(t.status)}</p>
              <p className="meta">
                <Link href={`/admin/tournaments/${t.id}`}>Открыть управление</Link>
              </p>
            </div>
          ))}
        </section>
      </div>

      <section className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Пользователь</th>
              <th>Текст</th>
              <th>Статус</th>
              <th>Ответ</th>
            </tr>
          </thead>
          <tbody>
            {suggestions.map((s) => (
              <tr key={s.id}>
                <td>{s.id}</td>
                <td>{s.user_id}</td>
                <td>{s.text}</td>
                <td>{statusLabelRu(s.status)}</td>
                <td>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      value={replyMap[s.id] || ''}
                      onChange={(e) => setReplyMap((prev) => ({ ...prev, [s.id]: e.target.value }))}
                      placeholder="Текст ответа"
                    />
                    <button type="button" className="btn" onClick={() => onReply(s.id)}>
                      Отправить
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
