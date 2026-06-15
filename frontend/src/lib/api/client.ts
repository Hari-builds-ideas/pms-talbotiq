import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";
import { emitForcedLogout, tokenStore } from "@/lib/auth/tokenStore";

/**
 * The single axios instance every API call goes through.
 * - Attaches `Authorization: Bearer <access>` (never a tenant id — it's in the JWT).
 * - On a 401, refreshes once via /auth/token/refresh, then retries; on failure,
 *   clears tokens and broadcasts a forced logout.
 * When VITE_USE_MOCKS=true, MSW intercepts these requests in the browser; the
 * same typed functions in endpoints.ts are used either way.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  // Reasonable ceiling so a hung AI seam doesn't wedge the UI.
  timeout: 30_000,
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.getAccess();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

let refreshInFlight: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  const refresh = tokenStore.getRefresh();
  if (!refresh) return null;
  try {
    // A bare axios call so we don't recurse through this interceptor.
    const res = await axios.post(
      `${BASE_URL}/auth/token/refresh`,
      { refresh },
      { headers: { "Content-Type": "application/json" } },
    );
    const access = (res.data as { access?: string }).access ?? null;
    const newRefresh = (res.data as { refresh?: string }).refresh ?? refresh;
    tokenStore.set(access, newRefresh);
    return access;
  } catch {
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    const status = error.response?.status;

    const isRefreshCall = original?.url?.includes("/auth/token/refresh");
    const isLoginCall = original?.url?.includes("/auth/login");

    if (
      status === 401 &&
      original &&
      !original._retried &&
      !isRefreshCall &&
      !isLoginCall &&
      tokenStore.getRefresh()
    ) {
      original._retried = true;
      // De-dupe concurrent refreshes.
      refreshInFlight = refreshInFlight ?? performRefresh();
      const newAccess = await refreshInFlight;
      refreshInFlight = null;

      if (newAccess) {
        original.headers.set("Authorization", `Bearer ${newAccess}`);
        return api(original);
      }
      tokenStore.clear();
      emitForcedLogout();
    }

    return Promise.reject(error);
  },
);
