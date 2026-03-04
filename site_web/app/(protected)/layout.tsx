'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { AppShell } from '@/components/app-shell';
import { useSession } from '@/components/session-provider';

export default function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { ready, session } = useSession();

  useEffect(() => {
    if (ready && !session) {
      router.replace('/login');
    }
  }, [ready, session, router]);

  if (!ready || !session) {
    return (
      <div className="page-wrap">
        <section className="hero-phone">
          <p className="hero-subtitle">Проверяю авторизацию...</p>
        </section>
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
