export type Session = {
  accessToken: string;
  refreshToken: string;
  userId: number;
  isAdmin: boolean;
};

const STORAGE_KEY = 'vzale.session.v1';

export function getStoredSession(): Session | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Session;
    if (!parsed.accessToken || !parsed.refreshToken || !parsed.userId) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function setStoredSession(session: Session): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearStoredSession(): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.removeItem(STORAGE_KEY);
}
