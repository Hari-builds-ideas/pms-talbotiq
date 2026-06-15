import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi, billingApi } from "@/lib/api/endpoints";
import type { FeatureFlags, Me, TokenPair } from "@/lib/types";
import type { FeatureKey, Role } from "@/lib/enums";
import { ROLE_RANK } from "@/lib/enums";
import {
  AUTH_LOGOUT_EVENT,
  tokenStore,
} from "@/lib/auth/tokenStore";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  me: Me | null;
  features: FeatureFlags | null;
  /** Finish a login once tokens are in hand (post-password or post-MFA). */
  completeLogin: (tokens: TokenPair) => Promise<void>;
  logout: () => Promise<void>;
  refreshFeatures: () => Promise<void>;
  /** Dev-only convenience: re-bootstrap as another seeded role (mocks). */
  hasFeature: (key: FeatureKey) => boolean;
  /** True when the current role is at least `min` (display gating only). */
  atLeast: (min: Role) => boolean;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = React.useState<AuthStatus>("loading");
  const [me, setMe] = React.useState<Me | null>(null);
  const [features, setFeatures] = React.useState<FeatureFlags | null>(null);

  const bootstrap = React.useCallback(async () => {
    if (!tokenStore.hasSession()) {
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
      tokenStore.clear();
      setMe(null);
      setFeatures(null);
      setStatus("unauthenticated");
    }
  }, []);

  React.useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  // React to a forced logout from the axios refresh interceptor.
  React.useEffect(() => {
    function onForcedLogout() {
      setMe(null);
      setFeatures(null);
      setStatus("unauthenticated");
      queryClient.clear();
    }
    window.addEventListener(AUTH_LOGOUT_EVENT, onForcedLogout);
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, onForcedLogout);
  }, [queryClient]);

  const completeLogin = React.useCallback(
    async (tokens: TokenPair) => {
      tokenStore.set(tokens.access, tokens.refresh);
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
    tokenStore.clear();
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
    status,
    me,
    features,
    completeLogin,
    logout,
    refreshFeatures,
    hasFeature,
    atLeast,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
