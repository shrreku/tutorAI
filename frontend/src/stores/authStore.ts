/**
 * Lightweight auth store backed by localStorage.
 *
 * Keeps the JWT token, basic user info, and exposes helpers for
 * login / register / logout that the rest of the app can import.
 */

export interface AuthUser {
  id: string;
  email: string | null;
  display_name: string | null;
  consent_training_global: boolean;
}

export interface AuthState {
  token: string | null;
  user: AuthUser | null;
}

const TOKEN_KEY = 'auth_token';
const USER_KEY  = 'auth_user';

// ---------------------------------------------------------------------------
// Read persisted state
// ---------------------------------------------------------------------------

function loadToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

function loadUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

// ---------------------------------------------------------------------------
// Write helpers
// ---------------------------------------------------------------------------

export function persistAuth(token: string, user: AuthUser): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  // Notify any mounted components
  window.dispatchEvent(new Event('auth-change'));
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new Event('auth-change'));
}

// ---------------------------------------------------------------------------
// Getters (synchronous, for imperative reads)
// ---------------------------------------------------------------------------

export function getToken(): string | null {
  return loadToken();
}

export function getUser(): AuthUser | null {
  return loadUser();
}

function isJwtExpired(token: string): boolean {
  try {
    const parts = token.split('.');
    if (parts.length < 2) {
      return false;
    }

    const payloadJson = atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'));
    const payload = JSON.parse(payloadJson) as { exp?: number };
    if (!payload.exp || typeof payload.exp !== 'number') {
      return false;
    }

    const nowSeconds = Math.floor(Date.now() / 1000);
    return payload.exp <= nowSeconds;
  } catch {
    return false;
  }
}

export function isAuthenticated(): boolean {
  const token = loadToken();
  if (!token) {
    return false;
  }
  if (isJwtExpired(token)) {
    clearAuth();
    return false;
  }
  return true;
}
