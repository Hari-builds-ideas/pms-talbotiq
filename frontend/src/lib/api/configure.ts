import { configureApiClient } from "@shared/api/client";
import { tokenStore, emitForcedLogout } from "@/lib/auth/tokenStore";

/**
 * Wire the shared API client for the WEB platform: the localStorage/memory token
 * store, the Vite base URL, and the window-event forced-logout broadcast. Called
 * once at bootstrap (main.tsx) and in the test setup, BEFORE any request — mobile
 * does the equivalent with expo-secure-store + the Expo env.
 */
export function configureWebApiClient(): void {
  configureApiClient({
    baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api",
    tokenStore,
    onForcedLogout: emitForcedLogout,
  });
}
