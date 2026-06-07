import { useSalary } from "@/api/hooks";
import { WidgetWrapper } from "@/components/WidgetWrapper";
import { useFilters } from "@/context/FilterContext";
import { formatPercent, formatSalary } from "@/lib/format";
import {
    Bar,
    BarChart,
    Cell,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

const PERCENTILE_COLORS = [
  "#e2e8f0",
  "#94a3b8",
  "#3b82f6",
  "#94a3b8",
  "#e2e8f0",
];
const PERCENTILE_LABELS = ["P10", "P25", "P50 (медиана)", "P75", "P90"];

interface ChartPayloadEntry {
  payload: { name: string };
  value: number;
}

function SalaryTooltip({
  active,
  payload,
  currency,
}: {
  active?: boolean;
  payload?: ChartPayloadEntry[];
  currency: string;
}) {
  if (!active || !payload?.[0]) return null;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{payload[0].payload.name}</p>
      <p>{formatSalary(Number(payload[0].value), currency)}</p>
    </div>
  );
}

export function SalaryWidget() {
  const { filters } = useFilters();
  const { data, isLoading, isError, error, refetch } = useSalary(filters);

  const d = data?.data;
  const meta = data?.meta;

  const chartData = d
    ? [
        { name: "P10", value: d.percentiles.p10 },
        { name: "P25", value: d.percentiles.p25 },
        { name: "P50", value: d.percentiles.p50 },
        { name: "P75", value: d.percentiles.p75 },
        { name: "P90", value: d.percentiles.p90 },
      ]
    : [];

  return (
    <WidgetWrapper
      title="Зарплаты"
      description={
        d
          ? `${d.currency} ${d.salary_basis} • Раскрытие: ${formatPercent(d.salary_disclosure_rate)}`
          : undefined
      }
      isLoading={isLoading}
      isError={isError}
      error={error}
      isEmpty={!d}
      lowConfidence={meta?.low_confidence}
      onRetry={() => refetch()}
    >
      {d && (
        <>
          {/* Key salary figures */}
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="text-center">
              <p className="text-xs text-muted-foreground">Минимум</p>
              <p className="text-sm font-semibold">
                {formatSalary(d.min, d.currency)}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs text-muted-foreground">Медиана</p>
              <p className="text-lg font-bold text-primary">
                {formatSalary(d.median, d.currency)}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs text-muted-foreground">Максимум</p>
              <p className="text-sm font-semibold">
                {formatSalary(d.max, d.currency)}
              </p>
            </div>
          </div>

          {/* Percentiles bar chart */}
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData}>
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis
                tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
                tick={{ fontSize: 11 }}
                width={50}
              />
              <Tooltip
                content={<SalaryTooltip currency={d.currency} />}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={PERCENTILE_COLORS[i]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          <div className="flex justify-center gap-3 mt-2 flex-wrap">
            {PERCENTILE_LABELS.map((label, i) => (
              <div key={label} className="flex items-center gap-1 text-xs">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-sm"
                  style={{ backgroundColor: PERCENTILE_COLORS[i] }}
                />
                {label}
              </div>
            ))}
          </div>

          {/* Range average */}
          {d.range_avg && (
            <p className="text-xs text-muted-foreground text-center mt-2">
              Средний диапазон вилок:{" "}
              {formatSalary(d.range_avg.from, d.currency)} –{" "}
              {formatSalary(d.range_avg.to, d.currency)}
            </p>
          )}

          <p className="text-xs text-muted-foreground text-center mt-1">
            Среднее: {formatSalary(d.mean, d.currency)} • Выборка:{" "}
            {meta?.sample_size ?? "—"}
          </p>
        </>
      )}
    </WidgetWrapper>
  );
}
