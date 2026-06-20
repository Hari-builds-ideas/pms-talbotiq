import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi, billingApi } from "@/lib/api/endpoints";
import type { Role } from "@/lib/enums";

const USERS_KEY = ["admin", "users"];
const TENANT_KEY = ["admin", "tenant-config"];
const ENTITLEMENT_KEY = ["billing", "entitlement"];
const FLAGS_KEY = ["billing", "feature-flags"];
const UPGRADE_KEY = ["billing", "upgrade-prompt"];

export function useUsers() {
  return useQuery({ queryKey: USERS_KEY, queryFn: adminApi.users });
}

export function useUserMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: USERS_KEY });
    void qc.invalidateQueries({ queryKey: ["org", "tree"] });
  };

  return {
    create: useMutation({
      mutationFn: adminApi.createUser,
      onSuccess: invalidate,
    }),
    setRole: useMutation({
      mutationFn: (v: { id: string; role: Role }) => adminApi.setRole(v.id, v.role),
      onSuccess: invalidate,
    }),
    setReportingLine: useMutation({
      mutationFn: (v: { id: string; manager: string | null }) =>
        adminApi.setReportingLine(v.id, v.manager),
      onSuccess: invalidate,
    }),
    setDisplayName: useMutation({
      mutationFn: (v: { id: string; display_name: string | null }) =>
        adminApi.setDisplayName(v.id, v.display_name),
      onSuccess: invalidate,
    }),
    deactivate: useMutation({
      mutationFn: (id: string) => adminApi.deactivate(id),
      onSuccess: invalidate,
    }),
    reactivate: useMutation({
      mutationFn: (id: string) => adminApi.reactivate(id),
      onSuccess: invalidate,
    }),
  };
}

export function useTenantConfig() {
  return useQuery({ queryKey: TENANT_KEY, queryFn: adminApi.tenantConfig });
}

export function useSaveTenantConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ settings, version }: { settings: Record<string, unknown>; version?: number }) =>
      adminApi.saveTenantConfig(settings, version),
    onSuccess: (data) => qc.setQueryData(TENANT_KEY, data),
  });
}

export function useEntitlement() {
  return useQuery({ queryKey: ENTITLEMENT_KEY, queryFn: billingApi.entitlement });
}
export function useFeatureFlags() {
  return useQuery({ queryKey: FLAGS_KEY, queryFn: billingApi.featureFlags });
}
export function useUpgradePrompt() {
  return useQuery({ queryKey: UPGRADE_KEY, queryFn: billingApi.upgradePrompt });
}

export function useBillingMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ENTITLEMENT_KEY });
    void qc.invalidateQueries({ queryKey: FLAGS_KEY });
    void qc.invalidateQueries({ queryKey: UPGRADE_KEY });
    // The whole app reads feature availability — refresh the bootstrap map too.
    void qc.invalidateQueries({ queryKey: ["billing", "my-features"] });
  };
  return {
    upgrade: useMutation({
      mutationFn: () => billingApi.upgrade({ pack: "FULL_AI" }),
      onSuccess: invalidate,
    }),
    setSeats: useMutation({
      mutationFn: (seat_count: number) => billingApi.setSeats({ seat_count }),
      onSuccess: invalidate,
    }),
  };
}
