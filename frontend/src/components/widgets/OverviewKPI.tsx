import { useIngestionStatus, useOverview } from "@/api/hooks";
import { Badge } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useFilters } from "@/context/FilterContext";
import {
    formatFreshness,
    formatGrowth,
    formatNumber,
    formatPercent,
    formatSalary,
} from "@/lib/format";
import {
    Banknote,
    Briefcase,
    Clock,
    Eye,
    TrendingDown,
    TrendingUp,
} from "lucide-react";

export function OverviewKPI() {
  const { filters } = useFilters();
  const { data, isLoading, isError } = useOverview(filters);
  const { data: ingestion } = useIngestionStatus();

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="rounded-lg border bg-card p-4 shadow-sm space-y-2"
          >
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-8 w-32" />
          </div>
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border bg-card p-4 shadow-sm text-center text-muted-foreground">
        Не удалось загрузить сводку
      </div>
    );
  }

  const d = data.data;
  const meta = data.meta;
  const growthPositive = d.demand_growth_mom >= 0;

  const cards = [
    {
      label: "Медианная зарплата",
      value: formatSalary(d.salary?.median, meta.currency || "RUB"),
      sub: `P25–P75: ${formatSalary(d.salary?.p25, meta.currency || "RUB")} – ${formatSalary(d.salary?.p75, meta.currency || "RUB")}`,
      icon: Banknote,
      color: "text-green-600",
    },
    {
      label: "Всего вакансий",
      value: formatNumber(d.total_vacancies),
      sub: `Раскрытие ЗП: ${formatPercent(d.salary_disclosure_rate)}`,
      icon: Briefcase,
      color: "text-blue-600",
    },
    {
      label: "Рост спроса (MoM)",
      value: formatGrowth(d.demand_growth_mom),
      sub: growthPositive ? "Рост" : "Снижение",
      icon: growthPositive ? TrendingUp : TrendingDown,
      color: growthPositive ? "text-green-600" : "text-red-600",
    },
    {
      label: "Свежесть данных",
      value: formatFreshness(ingestion?.data_freshness_hours),
      sub: ingestion?.last_run?.status
        ? `Статус: ${ingestion.last_run.status}`
        : "—",
      icon: Clock,
      color: "text-purple-600",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-lg border bg-card p-4 shadow-sm"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted-foreground font-medium">
              {card.label}
            </span>
            <card.icon className={`h-4 w-4 ${card.color}`} />
          </div>
          <div className="text-xl font-bold">{card.value}</div>
          <p className="text-xs text-muted-foreground mt-1">{card.sub}</p>
          {meta.low_confidence && (
            <Badge variant="warning" className="mt-1">
              <Eye className="h-3 w-3 mr-1" />
              Мало данных
            </Badge>
          )}
        </div>
      ))}
    </div>
  );
}
