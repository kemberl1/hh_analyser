import type {
  ApiEnvelope,
  CooccurrenceData,
  DemandData,
  DistributionBy,
  DistributionData,
  EmployersData,
  IngestionStatusResponse,
  MarketInsightResponse,
  MetricFilters,
  OverviewData,
  SalaryData,
  SalaryTimeseriesData,
  SkillsData,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL || "";
const BASE = `${API_URL}/api/v1`;

function buildParams(
  filters: MetricFilters,
  extra?: Record<string, string | number | undefined>
): string {
  const params = new URLSearchParams();
  if (filters.period) params.set("period", filters.period);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.grade && filters.grade !== "all")
    params.set("grade", filters.grade);
  if (filters.currency) params.set("currency", filters.currency);
  if (filters.salary_basis) params.set("salary_basis", filters.salary_basis);
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v !== undefined) params.set(k, String(v));
    }
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    let message = `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(text);
      if (parsed?.error?.message) message = parsed.error.message;
      else if (parsed?.detail) message = String(parsed.detail);
    } catch {
      // use default message
    }
    throw new Error(message);
  }
  return res.json();
}

// ===== Fetchers =====

export function fetchOverview(
  filters: MetricFilters
): Promise<ApiEnvelope<OverviewData>> {
  return fetchJson(`${BASE}/metrics/overview${buildParams(filters)}`);
}

export function fetchSalary(
  filters: MetricFilters
): Promise<ApiEnvelope<SalaryData>> {
  return fetchJson(`${BASE}/metrics/salary${buildParams(filters)}`);
}

export function fetchSalaryTimeseries(
  filters: MetricFilters
): Promise<ApiEnvelope<SalaryTimeseriesData>> {
  return fetchJson(`${BASE}/metrics/salary/timeseries${buildParams(filters)}`);
}

export function fetchSkills(
  filters: MetricFilters,
  limit?: number
): Promise<ApiEnvelope<SkillsData>> {
  return fetchJson(
    `${BASE}/metrics/skills${buildParams(filters, { limit })}`
  );
}

export function fetchCooccurrence(
  filters: MetricFilters,
  limit?: number
): Promise<ApiEnvelope<CooccurrenceData>> {
  return fetchJson(
    `${BASE}/metrics/skills/cooccurrence${buildParams(filters, { limit })}`
  );
}

export function fetchEmployers(
  filters: MetricFilters,
  limit?: number
): Promise<ApiEnvelope<EmployersData>> {
  return fetchJson(
    `${BASE}/metrics/employers${buildParams(filters, { limit })}`
  );
}

export function fetchDemand(
  filters: MetricFilters
): Promise<ApiEnvelope<DemandData>> {
  return fetchJson(`${BASE}/metrics/demand${buildParams(filters)}`);
}

export function fetchDistribution(
  filters: MetricFilters,
  by: DistributionBy
): Promise<ApiEnvelope<DistributionData>> {
  return fetchJson(
    `${BASE}/metrics/distribution${buildParams(filters, { by })}`
  );
}

export function fetchIngestionStatus(): Promise<IngestionStatusResponse> {
  return fetchJson(`${BASE}/ingestion/status`);
}

// ===== Phase 6: Market Insights =====

export function fetchMarketInsight(
  filters: MetricFilters
): Promise<MarketInsightResponse> {
  return fetchJson(`${BASE}/insights/market${buildParams(filters)}`);
}
