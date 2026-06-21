import * as SecureStore from "expo-secure-store";
import type { TokenStore } from "@shared/api/client";

/**
 * Token store backed by expo-secure-store (Keychain/Keystore) — NEVER
 * AsyncStorage/localStorage. The shared API client reads tokens SYNCHRONOUSLY in
 * its interceptors, but SecureStore is async, so we keep a sync in-memory cache
 * that is hydrated from SecureStore once at startup (`hydrateTokens`) and
 * write-through persisted on every change.
 */
const ACCESS_KEY = "pms.access";
const REFRESH_KEY = "pms.refresh";

let access: string | null = null;
let refresh: string | null = null;

export const secureTokenStore: TokenStore = {
  getAccess: () => access,
  getRefresh: () => refresh,
  set(a, r) {
    access = a;
    refresh = r;
    void (a ? SecureStore.setItemAsync(ACCESS_KEY, a) : SecureStore.deleteItemAsync(ACCESS_KEY));
    void (r ? SecureStore.setItemAsync(REFRESH_KEY, r) : SecureStore.deleteItemAsync(REFRESH_KEY));
  },
  clear() {
    access = null;
    refresh = null;
    void SecureStore.deleteItemAsync(ACCESS_KEY);
    void SecureStore.deleteItemAsync(REFRESH_KEY);
  },
};

/** Load any persisted session into the sync cache. Await BEFORE the first request. */
export async function hydrateTokens(): Promise<void> {
  access = await SecureStore.getItemAsync(ACCESS_KEY);
  refresh = await SecureStore.getItemAsync(REFRESH_KEY);
}

export function hasSession(): boolean {
  return Boolean(access || refresh);
}
