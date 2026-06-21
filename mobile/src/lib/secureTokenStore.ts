import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import type { TokenStore } from "@shared/api/client";

/**
 * Token store backed by expo-secure-store (Keychain/Keystore) on native — NEVER
 * AsyncStorage/localStorage on device. expo-secure-store is native-only and throws
 * on web ("getValueWithKeyAsync is not a function"), so the web target falls back
 * to localStorage (refresh) — access lives in memory either way.
 *
 * The shared API client reads tokens SYNCHRONOUSLY, but the persistent stores are
 * async, so a sync in-memory cache is hydrated once at startup (`hydrateTokens`)
 * and write-through persisted on every change.
 */
const ACCESS_KEY = "pms.access";
const REFRESH_KEY = "pms.refresh";
const isWeb = Platform.OS === "web";

let access: string | null = null;
let refresh: string | null = null;

async function persist(key: string, value: string | null): Promise<void> {
  if (isWeb) {
    try {
      if (value == null) globalThis.localStorage?.removeItem(key);
      else globalThis.localStorage?.setItem(key, value);
    } catch {
      /* storage unavailable — in-memory still works for the session */
    }
    return;
  }
  if (value == null) await SecureStore.deleteItemAsync(key);
  else await SecureStore.setItemAsync(key, value);
}

async function read(key: string): Promise<string | null> {
  if (isWeb) {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(key);
}

export const secureTokenStore: TokenStore = {
  getAccess: () => access,
  getRefresh: () => refresh,
  set(a, r) {
    access = a;
    refresh = r;
    void persist(ACCESS_KEY, a);
    void persist(REFRESH_KEY, r);
  },
  clear() {
    access = null;
    refresh = null;
    void persist(ACCESS_KEY, null);
    void persist(REFRESH_KEY, null);
  },
};

/** Load any persisted session into the sync cache. Await BEFORE the first request. */
export async function hydrateTokens(): Promise<void> {
  access = await read(ACCESS_KEY);
  refresh = await read(REFRESH_KEY);
}

export function hasSession(): boolean {
  return Boolean(access || refresh);
}
