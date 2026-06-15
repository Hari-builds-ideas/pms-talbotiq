/**
 * Token storage. The access token lives in memory only (never persisted).
 * The refresh token is kept in localStorage so a page reload can re-bootstrap
 * the session — in a hardened deployment this would move to an http-only cookie
 * issued by a backend-for-frontend. Authorization decisions are ALWAYS the
 * server's; we only read the role from /api/auth/me for routing.
 */

const REFRESH_KEY = "pms.refresh";

let accessToken: string | null = null;

export const tokenStore = {
  getAccess(): string | null {
    return accessToken;
  },
  setAccess(token: string | null): void {
    accessToken = token;
  },
  getRefresh(): string | null {
    try {
      return localStorage.getItem(REFRESH_KEY);
    } catch {
      return null;
    }
  },
  setRefresh(token: string | null): void {
    try {
      if (token) localStorage.setItem(REFRESH_KEY, token);
      else localStorage.removeItem(REFRESH_KEY);
    } catch {
      /* storage unavailable — in-memory access still works for the session */
    }
  },
  set(access: string | null, refresh: string | null): void {
    this.setAccess(access);
    this.setRefresh(refresh);
  },
  clear(): void {
    accessToken = null;
    this.setRefresh(null);
  },
  hasSession(): boolean {
    return Boolean(accessToken || this.getRefresh());
  },
};

/** Broadcast a forced logout (refresh failed) so the app can redirect to login. */
export const AUTH_LOGOUT_EVENT = "pms:auth-logout";
export function emitForcedLogout(): void {
  window.dispatchEvent(new CustomEvent(AUTH_LOGOUT_EVENT));
}
