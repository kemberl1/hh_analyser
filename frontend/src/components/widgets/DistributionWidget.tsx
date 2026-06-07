import { useDistribution } from "@/api/hooks";
import type { DistributionBy } from "@/api/types";
import { TabSelect } from "@/components/ui/select";
import { WidgetWrapper } from "@/components/WidgetWrapper";
import { useFilters } from "@/context/FilterContext";
import { formatNumber, formatPercent } from "@/lib/format";
import { useState } from "react";
import {
    Cell,
    Legend,
    Pie,
    PieChart,
    ResponsiveContainer,
    Tooltip,
} from "recharts";

const BY_OPTIONS = [
  { value: "grade", label: "Грейд" },
  { value: "format", label: "Формат" },
  { value: "experience", label: "Опыт" },
];

const COLORS = [
  "#3b82f6",
  "#8b5cf6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#06b6d4",
  "#ec4899",
  "#6366f1",
];

interface DistPayloadEntry {
  payload: { label: string; count: number; share: number };
  value: number;
  name: string;
}

function DistTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: DistPayloadEntry[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{row.label}</p>
      <p>Вакансий: {formatNumber(row.count)}</p>
      <p>Доля: {formatPercent(row.share)}</p>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function renderLabel(props: any) {
  const name = String(props?.name ?? "");
  const percent =
    typeof props?.percent === "number"
      ? `${(props.percent * 100).toFixed(0)}%`
      : "";
  return `${name} ${percent}`;
}

export function DistributionWidget() {
  const { filters } = useFilters();
  const [by, setBy] = useState<DistributionBy>("grade");
  const { data, isLoading, isError, error, refetch } = useDistribution(
    filters,
    by
  );

  const meta = data?.meta;
  const items = data?.data.distribution ?? [];

  return (
    <WidgetWrapper
      title="Распределения"
      isLoading={isLoading}
      isError={isError}
      error={error}
      isEmpty={items.length === 0}
      lowConfidence={meta?.low_confidence}
      onRetry={() => refetch()}
    >
      <div className="mb-4">
        <TabSelect
          value={by}
          onValueChange={(v) => setBy(v as DistributionBy)}
          options={BY_OPTIONS}
        />
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={items}
            dataKey="count"
            nameKey="label"
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={100}
            paddingAngle={2}
            label={renderLabel}
          >
            {items.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip content={<DistTooltip />} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </WidgetWrapper>
  );
}
