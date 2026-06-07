// ===== Common types =====

export type Period = "day" | "week" | "month" | "year";
export type Grade = "all" | "junior" | "middle" | "senior";
export type Currency = "RUB" | "USD" | "EUR";
export type SalaryBasis = "net" | "gross";
export type DistributionBy = "grade" | "format" | "experience";

export interface MetricFilters {
  period?: Period;
  date_from?: string;
  date_to?: string;
  grade?: Grade;
  currency?: Currency;
  salary_basis?: SalaryBasis;
}

export interface MetricMeta {
  period?: string;
  date_from?: string;
  date_to?: string;
  grade?: string;
  currency?: string;
  salary_basis?: string;
  computed_at?: string;
  low_confidence?: boolean;
  sample_size?: number;
  by?: string;
}

export interface ApiEnvelope<T> {
  meta: MetricMeta;
  data: T;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// ===== /metrics/salary =====

export interface SalaryPercentiles {
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

export interface SalaryRangeAvg {
  from: number;
  to: number;
}

export interface SalaryData {
  median: number;
  min: number;
  max: number;
  mean: number;
  percentiles: SalaryPercentiles;
  range_avg: SalaryRangeAvg;
  salary_disclosure_rate: number;
  currency: string;
  salary_basis: string;
}

// ===== /metrics/salary/timeseries =====

export interface SalaryTimeseriesPoint {
  period_start: string;
  median: number;
  p25: number;
  p75: number;
  count: number;
}

export interface SalaryTimeseriesData {
  points: SalaryTimeseriesPoint[];
}

// ===== /metrics/skills =====

export interface SkillItem {
  skill: string;
  canonical: string;
  count: number;
  share: number;
}

export interface SkillsData {
  skills: SkillItem[];
}

// ===== /metrics/skills/cooccurrence =====

export interface CooccurrencePair {
  a: string;
  b: string;
  count: number;
  share: number;
}

export interface CooccurrenceData {
  pairs: CooccurrencePair[];
}

// ===== /metrics/employers =====

export interface EmployerItem {
  employer_id: number;
  name: string;
  count: number;
  share: number;
}

export interface EmployersData {
  employers: EmployerItem[];
  top10_concentration: number;
}

// ===== /metrics/demand =====

export interface DemandPoint {
  period_start: string;
  count: number;
  growth: number;
}

export interface DemandData {
  points: DemandPoint[];
}

// ===== /metrics/distribution =====

export interface DistributionItem {
  key: string;
  label: string;
  count: number;
  share: number;
}

export interface DistributionData {
  distribution: DistributionItem[];
}

// ===== /metrics/overview =====

export interface OverviewSalary {
  median: number;
  p25: number;
  p75: number;
}

export interface OverviewTopSkill {
  skill: string;
  share: number;
}

export interface OverviewTopEmployer {
  name: string;
  count: number;
}

export interface OverviewGradeDistribution {
  key: string;
  share: number;
}

export interface OverviewData {
  salary: OverviewSalary;
  total_vacancies: number;
  salary_disclosure_rate: number;
  top_skills: OverviewTopSkill[];
  top_employers: OverviewTopEmployer[];
  grade_distribution: OverviewGradeDistribution[];
  demand_growth_mom: number;
}

// ===== /ingestion/status =====

export interface IngestionLastRun {
  id: number;
  started_at: string;
  finished_at: string;
  status: string;
  found_total: number;
  created_count: number;
  updated_count: number;
  error_count: number;
  filtered_count: number;
  api_fallback_count: number;
  captcha_block_count: number;
}

export interface IngestionStatusResponse {
  last_run: IngestionLastRun | null;
  data_freshness_hours: number | null;
}

// ===== /insights/market (Phase 6) =====

export interface InsightMeta {
  period?: string;
  grade?: string;
  model?: string | null;
  generated_at?: string | null;
  cached?: boolean;
  llm_enabled?: boolean;
}

export interface InsightBasedOn {
  sample_size: number;
}

export interface InsightData {
  summary: string;
  highlights: string[];
  based_on: InsightBasedOn;
}

export interface MarketInsightResponse {
  meta: InsightMeta;
  data: InsightData;
}
