import { useSkills } from "@/api/hooks";
import { WidgetWrapper } from "@/components/WidgetWrapper";
import { useFilters } from "@/context/FilterContext";
import { formatPercent } from "@/lib/format";
import {
    Bar,
    BarChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

interface SkillPayloadEntry {
  payload: { skill: string; count: number; share: number };
  value: number;
}

function SkillTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: SkillPayloadEntry[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{row.skill}</p>
      <p>Вакансий: {row.count}</p>
      <p>Доля: {formatPercent(row.share)}</p>
    </div>
  );
}

export function SkillsWidget() {
  const { filters } = useFilters();
  const { data, isLoading, isError, error, refetch } = useSkills(filters, 15);

  const meta = data?.meta;
  const skills = data?.data.skills ?? [];

  return (
    <WidgetWrapper
      title="Топ навыков"
      description="По частоте упоминания в вакансиях"
      isLoading={isLoading}
      isError={isError}
      error={error}
      isEmpty={skills.length === 0}
      lowConfidence={meta?.low_confidence}
      onRetry={() => refetch()}
    >
      <ResponsiveContainer width="100%" height={Math.max(300, skills.length * 28)}>
        <BarChart data={skills} layout="vertical" margin={{ left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={(v: number) => formatPercent(v)}
            tick={{ fontSize: 11 }}
            domain={[0, "auto"]}
          />
          <YAxis
            type="category"
            dataKey="skill"
            width={100}
            tick={{ fontSize: 12 }}
          />
          <Tooltip content={<SkillTooltip />} />
          <Bar
            dataKey="share"
            fill="#8b5cf6"
            radius={[0, 4, 4, 0]}
            barSize={20}
          />
        </BarChart>
      </ResponsiveContainer>
    </WidgetWrapper>
  );
}
