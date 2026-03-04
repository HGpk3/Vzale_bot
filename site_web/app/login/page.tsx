'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import { useSession } from '@/components/session-provider';
import {
  ApiError,
  finishBotLoginSession,
  getBotLoginSessionStatus,
  login,
  startBotLoginSession,
} from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const { setSession } = useSession();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [botLoading, setBotLoading] = useState(false);
  const [botError, setBotError] = useState<string | null>(null);
  const [botSessionId, setBotSessionId] = useState<string | null>(null);
  const [botExpiresAt, setBotExpiresAt] = useState<string | null>(null);
  const [nowTs, setNowTs] = useState<number>(() => Date.now());

  const botUsername = process.env.NEXT_PUBLIC_BOT_USERNAME || 'vzalebb_bot';
  const deepLink = useMemo(() => {
    if (!botSessionId) return null;
    return `https://t.me/${botUsername}?start=login_${botSessionId}`;
  }, [botSessionId, botUsername]);

  const secondsLeft = useMemo(() => {
    if (!botExpiresAt) return null;
    const expiresTs = new Date(botExpiresAt).getTime();
    return Math.max(0, Math.floor((expiresTs - nowTs) / 1000));
  }, [botExpiresAt, nowTs]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const data = await login(username, password);
      setSession({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        userId: data.user_id,
        isAdmin: data.is_admin,
      });
      router.replace('/dashboard');
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Неожиданная ошибка входа');
      }
    } finally {
      setLoading(false);
    }
  }

  async function onStartBotLogin() {
    setBotLoading(true);
    setBotError(null);
    try {
      const data = await startBotLoginSession();
      setBotSessionId(data.session_id);
      setBotExpiresAt(data.expires_at);
    } catch (err) {
      if (err instanceof ApiError) {
        setBotError(err.message);
      } else {
        setBotError('Не удалось запустить вход через бота');
      }
    } finally {
      setBotLoading(false);
    }
  }

  useEffect(() => {
    if (!botSessionId) {
      return;
    }

    let active = true;
    let polling = false;

    const tick = async () => {
      if (!active || polling) {
        return;
      }
      polling = true;

      try {
        const status = await getBotLoginSessionStatus(botSessionId);
        if (!active) return;

        if (status.expired) {
          setBotError('Сессия входа истекла. Нажми "Войти через бота" ещё раз.');
          setBotSessionId(null);
          setBotExpiresAt(null);
          return;
        }

        if (status.consumed) {
          setBotError('Сессия уже использована. Запусти вход заново.');
          setBotSessionId(null);
          setBotExpiresAt(null);
          return;
        }

        if (status.approved) {
          const data = await finishBotLoginSession(botSessionId);
          if (!active) return;
          setSession({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            userId: data.user_id,
            isAdmin: data.is_admin,
          });
          router.replace('/dashboard');
        }
      } catch (err) {
        if (!active) return;
        if (err instanceof ApiError) {
          setBotError(err.message);
        } else {
          setBotError('Ошибка проверки статуса входа через бота');
        }
      } finally {
        polling = false;
      }
    };

    const interval = window.setInterval(tick, 2000);
    void tick();

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [botSessionId, router, setSession]);

  useEffect(() => {
    if (!botSessionId || !botExpiresAt) {
      return;
    }
    const timer = window.setInterval(() => setNowTs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [botSessionId, botExpiresAt]);

  const countdownLabel = useMemo(() => {
    if (secondsLeft === null) return null;
    const minutes = Math.floor(secondsLeft / 60);
    const seconds = secondsLeft % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }, [secondsLeft]);

  return (
    <div className="page-wrap reveal-up">
      <section className="hero-phone" style={{ maxWidth: 760, margin: '0 auto' }}>
        <span className="hero-kicker">Безопасный вход</span>
        <h1 className="hero-title">
          Вход в <strong>кабинет</strong>
        </h1>

        <div className="card" style={{ marginBottom: 14 }}>
          <h3>Войти через Telegram-бота (рекомендуется)</h3>
          <p>Нажми кнопку, открой бота и подтверди вход. Виджет Telegram не требуется.</p>
          <div className="hero-actions" style={{ marginTop: 10 }}>
            <button className="btn primary" onClick={onStartBotLogin} disabled={botLoading}>
              {botLoading ? 'Создаю сессию...' : 'Войти через бота'}
            </button>
          </div>

          {botSessionId ? (
            <div className="notice" style={{ marginTop: 10 }}>
              <p style={{ marginTop: 0 }}>Сессия создана. Подтверди вход в Telegram-боте.</p>
              {deepLink ? (
                <p>
                  <a href={deepLink} target="_blank" rel="noreferrer" className="btn primary">
                    Открыть бота
                  </a>
                </p>
              ) : null}
              <p>
                Если кнопка не сработала, отправь боту:
                <br />
                <code>/start login_{botSessionId}</code>
              </p>
              {countdownLabel ? <p>Осталось: <strong>{countdownLabel}</strong></p> : null}
              <p style={{ marginBottom: 0 }}>Жду подтверждение...</p>
            </div>
          ) : null}

          {botError ? <div className="notice error" style={{ marginTop: 10 }}>{botError}</div> : null}
        </div>

        <form className="form-panel" onSubmit={onSubmit}>
          <h3 style={{ margin: 0 }}>Вход по логину и паролю</h3>
          <label>
            Логин
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin" required />
          </label>

          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </label>

          {error ? <div className="notice error">{error}</div> : null}

          <button className="btn" type="submit" disabled={loading}>
            {loading ? 'Вхожу...' : 'Войти'}
          </button>
        </form>
      </section>
    </div>
  );
}
