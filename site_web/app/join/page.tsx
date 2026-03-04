import Link from 'next/link';

export default function JoinPage() {
  return (
    <div className="page-wrap reveal-up">
      <section className="hero-phone">
        <span className="hero-kicker">Новые игроки | VZALE</span>
        <h1 className="hero-title">
          Принять участие <strong>в VZALE</strong>
        </h1>
        <p className="hero-subtitle">
          Если ты новый игрок и хочешь попасть на турнир VZALE 3x3, начни с простого маршрута: изучи ближайшие
          турниры, создай аккаунт, вступи в команду или собери свою.
        </p>

        <div className="hero-actions">
          <Link className="btn primary" href="/public/tournaments">
            Посмотреть турниры
          </Link>
          <Link className="btn" href="/login">
            Создать/войти в аккаунт
          </Link>
          <Link className="btn ghost" href="/my/team">
            Собрать команду
          </Link>
        </div>
      </section>

      <section className="card-grid">
        <article className="card">
          <h3>Шаг 1. Выбери турнир</h3>
          <p>Открой предстоящие турниры VZALE и выбери событие, в котором хочешь участвовать.</p>
        </article>
        <article className="card">
          <h3>Шаг 2. Войди в систему</h3>
          <p>После входа доступна работа с командой, инвайт-кодами, статистикой и турнирными разделами.</p>
        </article>
        <article className="card">
          <h3>Шаг 3. Команда</h3>
          <p>Создай свою команду или вступи в существующую по приглашению капитана.</p>
        </article>
        <article className="card">
          <h3>Шаг 4. Готовность к игре</h3>
          <p>Следи за расписанием, статусами матчей и новостями турнира в личном кабинете VZALE.</p>
        </article>
      </section>

      <section className="hero-phone" style={{ marginTop: 14 }}>
        <h2 className="section-title" style={{ marginTop: 0 }}>
          Уже в теме?
        </h2>
        <div className="hero-actions" style={{ marginTop: 6 }}>
          <Link className="btn" href="/dashboard">
            В кабинет
          </Link>
          <Link className="btn" href="/tournaments">
            К турнирам
          </Link>
          <Link className="btn" href="/my/stats">
            К статистике
          </Link>
        </div>
      </section>
    </div>
  );
}
