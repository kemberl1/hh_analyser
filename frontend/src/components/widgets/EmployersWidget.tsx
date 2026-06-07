import { useEmployers } from "@/api/hooks";
import { WidgetWrapper } from "@/components/WidgetWrapper";
import { useFilters } from "@/context/FilterContext";
import { formatNumber, formatPercent } from "@/lib/format";
import {
    Bar,
    BarChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

interface EmpPayloadEntry {
  payload: { name: string; count: number; share: number };
  value: number;
}

function EmpTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: EmpPayloadEntry[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{row.name}</p>
      <p>Вакансий: {formatNumber(row.count)}</p>
      <p>Доля: {formatPercent(row.share)}</p>
    </div>
  );
}

export function EmployersWidget() {
  const { filters } = useFilters();
  const { data, isLoading, isError, error, refetch } = useEmployers(
    filters,
    10
  );

  const meta = data?.meta;
  const employers = data?.data.employers ?? [];
  const concentration = data?.data.top10_concentration;

  return (
    <WidgetWrapper
      title="Топ работодателей"
      description={
        concentration != null
          ? `Концентрация ТОП-10: ${formatPercent(concentration)}`
          : undefined
      }
      isLoading={isLoading}
      isError={isError}
      error={error}
      isEmpty={employers.length === 0}
      lowConfidence={meta?.low_confidence}
      onRetry={() => refetch()}
    >
      <ResponsiveContainer
        width="100%"
        height={Math.max(250, employers.length * 32)}
      >
        <BarChart data={employers} layout="vertical" margin={{ left: 0 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            className="stroke-muted"
            horizontal={false}
          />
          <XAxis
            type="number"
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => formatNumber(v)}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={120}
            tick={{ fontSize: 12 }}
          />
          <Tooltip content={<EmpTooltip />} />
          <Bar
            dataKey="count"
            fill="#10b981"
            radius={[0, 4, 4, 0]}
            barSize={22}
          />
        </BarChart>
      </ResponsiveContainer>
    </WidgetWrapper>
  );
}
