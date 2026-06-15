import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "@/lib/api/endpoints";

export function useIndividual(employee?: string) {
  return useQuery({
    queryKey: ["analytics", "individual", employee ?? "self"],
    queryFn: () => analyticsApi.individual(employee),
  });
}

export function useDepartment(head: string | undefined, cycle: string | undefined) {
  return useQuery({
    queryKey: ["analytics", "department", head, cycle],
    queryFn: () => analyticsApi.department(head as string, cycle as string),
    enabled: Boolean(head && cycle),
  });
}

export function useCalibration(cycle: string | undefined) {
  return useQuery({
    queryKey: ["analytics", "calibration", cycle],
    queryFn: () => analyticsApi.calibration(cycle as string),
    enabled: Boolean(cycle),
  });
}
