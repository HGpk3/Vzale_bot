'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { useSession } from '@/components/session-provider';

const nav = [
  { href: '/dashboard', label: 'Главная' },
  { href: '/tournaments', label: 'Турниры' },
  { href: '/my/team', label: 'Моя команда' },
  { href: '/my/achievements', label: 'Достижения' },
  { href: '/my/stats', label: 'Статистика' },
  { href: '/admin', label: 'Админка' },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { session, logout } = useSession();

  return (
    <div className="app-frame reveal-up">
      <aside className="app-sidebar">
        <p className="brand-kicker">VZALE LEAGUE</p>
        <h1 className="brand-title">Панель управления</h1>

        <nav className="nav-stack">
          {nav
            .filter((item) => (item.href.startsWith('/admin') ? session?.isAdmin : true))
            .map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link key={item.href} href={item.href} className={active ? 'nav-link active' : 'nav-link'}>
                  {item.label}
                </Link>
              );
            })}
        </nav>

        <div className="sidebar-foot">
          <p>Пользователь #{session?.userId}</p>
          <button className="btn ghost" onClick={logout}>
            Выйти
          </button>
        </div>
      </aside>

      <main className="app-main">{children}</main>
    </div>
  );
}
