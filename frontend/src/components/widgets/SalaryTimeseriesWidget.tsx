import { useSalaryTimeseries } from "@/api/hooks";
import { WidgetWrapper } from "@/components/WidgetWrapper";
import { useFilters } from "@/context/FilterContext";
import { formatPeriodLabel, formatSalary } from "@/lib/format";
import {
    Area,
    AreaChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

interface TsPayloadEntry {
  payload: { label: string };
  value: number;
  dataKey: string;
  color: string;
}

function TsTooltip({
  active,
  payload,
  currency,
}: {
  active?: boolean;
  payload?: TsPayloadEntry[];
  currency: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as { label: string; median: number; p25: number; p75: number; count: number };
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium mb-1">{row.label}</p>
      <p>Медиана: {formatSalary(row.median, currency)}</p>
      <p className="text-muted-foreground">
        P25–P75: {formatSalary(row.p25, currency)} – {formatSalary(row.p75, currency)}
      </p>
      <p className="text-muted-foreground">Вакансий: {row.count}</p>
    </div>
  );
}

export function SalaryTimeseriesWidget() {
  const { filters } = useFilters();
  const { data, isLoading, isError, error, refetch } =
    useSalaryTimeseries(filters);

  const meta = data?.meta;
  const chartData = (data?.data.points ?? []).map((p) => ({
    ...p,
    label: formatPeriodLabel(p.period_start),
  }));

  return (
    <WidgetWrapper
      title="Динамика зарплат"
      description="Медиана с полосой P25–P75"
      isLoading={isLoading}
      isError={isError}
      error={error}
      isEmpty={chartData.length === 0}
      lowConfidence={meta?.low_confidence}
      onRetry={() => refetch()}
    >
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis
            tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
            tick={{ fontSize: 11 }}
            width={50}
          />
          <Tooltip
            content={<TsTooltip currency={meta?.currency || "RUB"} />}
          />
          <Area
            type="monotone"
            dataKey="p75"
            stackId="band"
            stroke="none"
            fill="#dbeafe"
            fillOpacity={0.5}
          />
          <Area
            type="monotone"
            dataKey="p25"
            stackId="band"
            stroke="none"
            fill="#ffffff"
            fillOpacity={1}
          />
          <Area
            type="monotone"
            dataKey="median"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="none"
            dot={{ r: 3, fill: "#3b82f6" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </WidgetWrapper>
  );
}
