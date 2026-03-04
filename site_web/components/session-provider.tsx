'use client';

import { createContext, useContext, useEffect, useMemo, useState } from 'react';

import { clearStoredSession, getStoredSession, setStoredSession, type Session } from '@/lib/session';

type SessionContextType = {
  session: Session | null;
  ready: boolean;
  setSession: (next: Session | null) => void;
  logout: () => void;
};

const SessionContext = createContext<SessionContextType | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const existing = getStoredSession();
    setSessionState(existing);
    setReady(true);
  }, []);

  const setSession = (next: Session | null) => {
    setSessionState(next);
    if (next) {
      setStoredSession(next);
      return;
    }
    clearStoredSession();
  };

  const logout = () => setSession(null);

  const value = useMemo(() => ({ session, ready, setSession, logout }), [session, ready]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error('useSession must be used inside SessionProvider');
  }
  return ctx;
}
