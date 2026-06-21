import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi, billingApi } from "@shared/api/endpoints";
import type { FeatureFlags, Me, TokenPair } from "@shared/types";
import type { FeatureKey, Role } from "@shared/enums";
import { ROLE_RANK } from "@shared/enums";
import { hasSession, hydrateTokens, secureTokenStore } from "./secureTokenStore";
import { setForcedLogoutHandler } from "./api";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  me: Me | null;
  features: FeatureFlags | null;
  completeLogin: (tokens: TokenPair) => Promise<void>;
  logout: () => Promise<void>;
  refreshFeatures: () => Promise<void>;
  hasFeature: (key: FeatureKey) => boolean;
  atLeast: (min: Role) => boolean;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

/**
 * Mobile auth provider — the SAME state machine as web (`bootstrap` → me +
 * my-features; `completeLogin`; `logout`), only the storage (SecureStore) and the
 * forced-logout wiring (a callback, not a window event) differ per platform.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = React.useState<AuthStatus>("loading");
  const [me, setMe] = React.useState<Me | null>(null);
  const [features, setFeatures] = React.useState<FeatureFlags | null>(null);

  const bootstrap = React.useCallback(async () => {
    if (!hasSession()) {
      setStatus("unauthenticated");
      return;
    }
    try {
      const [user, flags] = await Promise.all([
        authApi.me(),
        billingApi.myFeatures().catch(() => null),
      ]);
      setMe(user);
      setFeatures(flags);
      setStatus("authenticated");
    } catch {
      secureTokenStore.clear();
      setMe(null);
      setFeatures(null);
      setStatus("unauthenticated");
    }
  }, []);

  // Hydrate persisted tokens from SecureStore, then bootstrap.
  React.useEffect(() => {
    void (async () => {
      await hydrateTokens();
      await bootstrap();
    })();
  }, [bootstrap]);

  // The shared refresh interceptor calls this when a refresh fails → drop to login.
  React.useEffect(() => {
    setForcedLogoutHandler(() => {
      setMe(null);
      setFeatures(null);
      setStatus("unauthenticated");
      queryClient.clear();
    });
  }, [queryClient]);

  const completeLogin = React.useCallback(
    async (tokens: TokenPair) => {
      secureTokenStore.set(tokens.access, tokens.refresh);
      setStatus("loading");
      await bootstrap();
    },
    [bootstrap],
  );

  const logout = React.useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* best-effort — clear locally regardless */
    }
    secureTokenStore.clear();
    setMe(null);
    setFeatures(null);
    setStatus("unauthenticated");
    queryClient.clear();
  }, [queryClient]);

  const refreshFeatures = React.useCallback(async () => {
    const flags = await billingApi.myFeatures().catch(() => null);
    setFeatures(flags);
  }, []);

  const hasFeature = React.useCallback(
    (key: FeatureKey) => Boolean(features?.[key]),
    [features],
  );
  const atLeast = React.useCallback(
    (min: Role) => (me ? ROLE_RANK[me.role] >= ROLE_RANK[min] : false),
    [me],
  );

  const value: AuthContextValue = {
    status, me, features, completeLogin, logout, refreshFeatures, hasFeature, atLeast,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
