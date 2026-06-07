import { useIngestionStatus } from "@/api/hooks";
import type { Currency, Grade, Period, SalaryBasis } from "@/api/types";
import { Badge, Select, TabSelect } from "@/components/ui/select";
import { useFilters } from "@/context/FilterContext";
import { formatFreshness } from "@/lib/format";
import { Clock, Search } from "lucide-react";

const PERIOD_OPTIONS = [
  { value: "day", label: "День" },
  { value: "week", label: "Неделя" },
  { value: "month", label: "Месяц" },
  { value: "year", label: "Год" },
];

const GRADE_OPTIONS = [
  { value: "all", label: "Все грейды" },
  { value: "junior", label: "Junior" },
  { value: "middle", label: "Middle" },
  { value: "senior", label: "Senior" },
];

const CURRENCY_OPTIONS = [
  { value: "RUB", label: "₽ RUB" },
  { value: "USD", label: "$ USD" },
  { value: "EUR", label: "€ EUR" },
];

const SALARY_BASIS_OPTIONS = [
  { value: "net", label: "На руки (net)" },
  { value: "gross", label: "До налогов (gross)" },
];

export function DashboardHeader() {
  const { state, setPeriod, setGrade, setCurrency, setSalaryBasis } =
    useFilters();
  const { data: ingestion } = useIngestionStatus();

  const freshness = ingestion?.data_freshness_hours;
  const isFresh = freshness != null && freshness < 24;

  return (
    <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto px-4 py-3">
        {/* Top row: brand + freshness */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Search className="h-5 w-5 text-primary" />
            <h1 className="text-lg font-bold">HH Analyser</h1>
            <span className="text-sm text-muted-foreground hidden sm:inline">
              — Рынок Frontend-вакансий
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              Обновлено: {formatFreshness(freshness)}
            </span>
            {freshness != null && (
              <Badge variant={isFresh ? "success" : "warning"}>
                {isFresh ? "Актуально" : "Устарело"}
              </Badge>
            )}
          </div>
        </div>

        {/* Filter row */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-muted-foreground">
              Период:
            </span>
            <TabSelect
              value={state.period}
              onValueChange={(v) => setPeriod(v as Period)}
              options={PERIOD_OPTIONS}
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-muted-foreground">
              Грейд:
            </span>
            <TabSelect
              value={state.grade}
              onValueChange={(v) => setGrade(v as Grade)}
              options={GRADE_OPTIONS}
            />
          </div>

          <div className="flex items-center gap-2">
            <Select
              value={state.currency}
              onValueChange={(v) => setCurrency(v as Currency)}
              options={CURRENCY_OPTIONS}
              className="w-28"
            />
          </div>

          <div className="flex items-center gap-2">
            <Select
              value={state.salary_basis}
              onValueChange={(v) => setSalaryBasis(v as SalaryBasis)}
              options={SALARY_BASIS_OPTIONS}
              className="w-44"
            />
          </div>
        </div>
      </div>
    </header>
  );
}
