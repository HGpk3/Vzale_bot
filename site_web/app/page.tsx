import Link from 'next/link';

export default function LandingPage() {
  return (
    <div className="page-wrap reveal-up">
      <section className="hero-phone">
        <span className="hero-kicker">VZALE | Уличный баскетбол 3x3</span>
        <h1 className="hero-title">
          VZALE <strong>турниры 3x3</strong>
        </h1>
        <p className="hero-subtitle">
          VZALE - организация коммерческих турниров по баскетболу 3x3 в уличном, стрит-ориентированном стиле.
          Здесь игроки, команды и капитаны получают понятную платформу: регистрация, информация о предстоящих
          турнирах, статистика и управление участием.
        </p>

        <div className="hero-actions">
          <Link className="btn primary" href="/public/tournaments">
            Предстоящие турниры
          </Link>
          <Link className="btn ghost" href="/login">
            Войти игроку
          </Link>
          <Link className="btn ghost" href="/dashboard">
            Турнирный кабинет
          </Link>
          <Link className="btn ghost" href="/my/stats">
            Моя статистика
          </Link>
          <Link className="btn warn" href="/join">
            Принять участие
          </Link>
        </div>

        <div className="kpi-grid">
          <article className="metric floaty">
            <p>Формат</p>
            <h3>3x3</h3>
          </article>
          <article className="metric floaty" style={{ animationDelay: '0.2s' }}>
            <p>Стиль</p>
            <h3>СТРИТ</h3>
          </article>
          <article className="metric floaty" style={{ animationDelay: '0.4s' }}>
            <p>Организация</p>
            <h3>VZALE</h3>
          </article>
          <article className="metric floaty" style={{ animationDelay: '0.6s' }}>
            <p>Платформа</p>
            <h3>ОНЛАЙН</h3>
          </article>
        </div>
      </section>

      <section className="card-grid">
        <article className="card">
          <h3>Что такое VZALE</h3>
          <p>
            VZALE проводит коммерческие турниры по баскетболу 3x3: от набора участников и регистрации команд до
            матчей, турнирной таблицы и индивидуальной статистики игроков.
          </p>
          <p className="meta">Стрит-вайб + спортивная дисциплина + прозрачная турнирная логика</p>
        </article>
        <article className="card">
          <h3>Для кого эта платформа</h3>
          <p>
            Для тех, кто уже в движении VZALE: быстрый доступ к турнирам, информации, командам и статистике.
            Для новых игроков - отдельный вход «Принять участие» с понятными шагами.
          </p>
          <p className="meta">Игроки / Капитаны / Организаторы</p>
        </article>
      </section>

      <section className="hero-phone" style={{ marginTop: 14 }}>
        <span className="tag">Быстрый старт</span>
        <h2 className="section-title" style={{ marginTop: 10 }}>
          Навигация VZALE
        </h2>
        <div className="hero-actions" style={{ marginTop: 8 }}>
          <Link className="btn" href="/public/tournaments">
            Смотреть турниры
          </Link>
          <Link className="btn" href="/login">
            Вход для участников
          </Link>
          <Link className="btn" href="/tournaments">
            Туры и сетка
          </Link>
          <Link className="btn" href="/my/team">
            Моя команда
          </Link>
          <Link className="btn" href="/join">
            Новичкам: как попасть
          </Link>
        </div>
      </section>
    </div>
  );
}
