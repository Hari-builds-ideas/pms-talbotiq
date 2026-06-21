import Constants from "expo-constants";
import { configureApiClient } from "@shared/api/client";
import { secureTokenStore } from "./secureTokenStore";

/**
 * Resolve the backend base URL for the device. Expo Go runs on the phone, so
 * `localhost` is the PHONE, not the Mac — derive the Mac's LAN IP from the Metro
 * host (`hostUri`, e.g. "192.168.1.5:8081") and target the backend on :8080.
 * Override with EXPO_PUBLIC_API_BASE_URL for a tunnel / a different host.
 */
function deriveBaseUrl(): string {
  const explicit = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (explicit) return explicit;
  const hostUri =
    Constants.expoConfig?.hostUri ?? Constants.expoGoConfig?.debuggerHost ?? "";
  const ip = String(hostUri).split(":")[0];
  return ip ? `http://${ip}:8080/api` : "http://localhost:8080/api";
}

let forcedLogoutHandler: () => void = () => {};
export function setForcedLogoutHandler(fn: () => void): void {
  forcedLogoutHandler = fn;
}

/** The resolved base URL (exposed so the UI can show which backend it's hitting). */
export const apiBaseUrl = deriveBaseUrl();

/** Wire the shared API client for mobile: SecureStore tokens + the derived base
 *  URL + a forced-logout callback the auth provider registers. Call once at boot. */
export function configureMobileApi(): void {
  configureApiClient({
    baseURL: apiBaseUrl,
    tokenStore: secureTokenStore,
    onForcedLogout: () => forcedLogoutHandler(),
  });
}
