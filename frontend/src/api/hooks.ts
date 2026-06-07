import { useQuery } from "@tanstack/react-query";
import {
    fetchCooccurrence,
    fetchDemand,
    fetchDistribution,
    fetchEmployers,
    fetchIngestionStatus,
    fetchOverview,
    fetchSalary,
    fetchSalaryTimeseries,
    fetchSkills,
} from "./client";
import type { DistributionBy, MetricFilters } from "./types";

/** Stable key factory — filters included so TanStack Query refetches on change */
const keys = {
  overview: (f: MetricFilters) => ["metrics", "overview", f] as const,
  salary: (f: MetricFilters) => ["metrics", "salary", f] as const,
  salaryTimeseries: (f: MetricFilters) =>
    ["metrics", "salary", "timeseries", f] as const,
  skills: (f: MetricFilters, limit?: number) =>
    ["metrics", "skills", f, limit] as const,
  cooccurrence: (f: MetricFilters, limit?: number) =>
    ["metrics", "skills", "cooccurrence", f, limit] as const,
  employers: (f: MetricFilters, limit?: number) =>
    ["metrics", "employers", f, limit] as const,
  demand: (f: MetricFilters) => ["metrics", "demand", f] as const,
  distribution: (f: MetricFilters, by: DistributionBy) =>
    ["metrics", "distribution", by, f] as const,
  ingestionStatus: () => ["ingestion", "status"] as const,
};

export function useOverview(filters: MetricFilters) {
  return useQuery({
    queryKey: keys.overview(filters),
    queryFn: () => fetchOverview(filters),
    staleTime: 60_000,
  });
}

export function useSalary(filters: MetricFilters) {
  return useQuery({
    queryKey: keys.salary(filters),
    queryFn: () => fetchSalary(filters),
    staleTime: 60_000,
  });
}

export function useSalaryTimeseries(filters: MetricFilters) {
  return useQuery({
    queryKey: keys.salaryTimeseries(filters),
    queryFn: () => fetchSalaryTimeseries(filters),
    staleTime: 60_000,
  });
}

export function useSkills(filters: MetricFilters, limit = 20) {
  return useQuery({
    queryKey: keys.skills(filters, limit),
    queryFn: () => fetchSkills(filters, limit),
    staleTime: 60_000,
  });
}

export function useCooccurrence(filters: MetricFilters, limit = 15) {
  return useQuery({
    queryKey: keys.cooccurrence(filters, limit),
    queryFn: () => fetchCooccurrence(filters, limit),
    staleTime: 60_000,
  });
}

export function useEmployers(filters: MetricFilters, limit = 10) {
  return useQuery({
    queryKey: keys.employers(filters, limit),
    queryFn: () => fetchEmployers(filters, limit),
    staleTime: 60_000,
  });
}

export function useDemand(filters: MetricFilters) {
  return useQuery({
    queryKey: keys.demand(filters),
    queryFn: () => fetchDemand(filters),
    staleTime: 60_000,
  });
}

export function useDistribution(filters: MetricFilters, by: DistributionBy) {
  return useQuery({
    queryKey: keys.distribution(filters, by),
    queryFn: () => fetchDistribution(filters, by),
    staleTime: 60_000,
  });
}

export function useIngestionStatus() {
  return useQuery({
    queryKey: keys.ingestionStatus(),
    queryFn: fetchIngestionStatus,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
