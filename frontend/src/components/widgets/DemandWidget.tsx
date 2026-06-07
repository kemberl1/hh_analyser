import { useDemand } from "@/api/hooks";
import { WidgetWrapper } from "@/components/WidgetWrapper";
import { useFilters } from "@/context/FilterContext";
import { formatGrowth, formatNumber, formatPeriodLabel } from "@/lib/format";
import {
    Bar,
    CartesianGrid,
    ComposedChart,
    Line,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis
} from "recharts";

interface DemandPayloadEntry {
  payload: { label: string; count: number; growth: number };
  value: number;
  dataKey: string;
}

function DemandTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: DemandPayloadEntry[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{row.label}</p>
      <p>Вакансий: {formatNumber(row.count)}</p>
      <p className={row.growth >= 0 ? "text-green-600" : "text-red-600"}>
        Рост: {formatGrowth(row.growth)}
      </p>
    </div>
  );
}

export function DemandWidget() {
  const { filters } = useFilters();
  const { data, isLoading, isError, error, refetch } = useDemand(filters);

  const meta = data?.meta;
  const chartData = (data?.data.points ?? []).map((p) => ({
    ...p,
    label: formatPeriodLabel(p.period_start),
    growthPct: p.growth * 100,
  }));

  return (
    <WidgetWrapper
      title="Динамика спроса"
      description="Число вакансий по периодам"
      isLoading={isLoading}
      isError={isError}
      error={error}
      isEmpty={chartData.length === 0}
      lowConfidence={meta?.low_confidence}
      onRetry={() => refetch()}
    >
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis
            yAxisId="count"
            tickFormatter={(v: number) => formatNumber(v)}
            tick={{ fontSize: 11 }}
            width={50}
          />
          <YAxis
            yAxisId="growth"
            orientation="right"
            tickFormatter={(v: number) => `${v.toFixed(0)}%`}
            tick={{ fontSize: 11 }}
            width={40}
          />
          <Tooltip content={<DemandTooltip />} />
          <Bar
            yAxisId="count"
            dataKey="count"
            fill="#60a5fa"
            radius={[4, 4, 0, 0]}
          />
          <Line
            yAxisId="growth"
            type="monotone"
            dataKey="growthPct"
            stroke="#f97316"
            strokeWidth={2}
            dot={{ r: 3, fill: "#f97316" }}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="flex justify-center gap-4 mt-2 text-xs">
        <div className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-blue-400" />
          Вакансий
        </div>
        <div className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-orange-500" />
          Рост (%)
        </div>
      </div>
    </WidgetWrapper>
  );
}
