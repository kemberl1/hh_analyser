import { useCooccurrence } from "@/api/hooks";
import { WidgetWrapper } from "@/components/WidgetWrapper";
import { useFilters } from "@/context/FilterContext";
import { formatPercent } from "@/lib/format";

export function CooccurrenceWidget() {
  const { filters } = useFilters();
  const { data, isLoading, isError, error, refetch } = useCooccurrence(
    filters,
    15
  );

  const meta = data?.meta;
  const pairs = data?.data.pairs ?? [];

  return (
    <WidgetWrapper
      title="Связки навыков"
      description="Топ пар навыков, встречающихся вместе"
      isLoading={isLoading}
      isError={isError}
      error={error}
      isEmpty={pairs.length === 0}
      lowConfidence={meta?.low_confidence}
      onRetry={() => refetch()}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="pb-2 font-medium text-muted-foreground">#</th>
              <th className="pb-2 font-medium text-muted-foreground">
                Навык A
              </th>
              <th className="pb-2 font-medium text-muted-foreground">
                Навык B
              </th>
              <th className="pb-2 font-medium text-muted-foreground text-right">
                Вакансий
              </th>
              <th className="pb-2 font-medium text-muted-foreground text-right">
                Доля
              </th>
            </tr>
          </thead>
          <tbody>
            {pairs.map((pair, i) => (
              <tr
                key={`${pair.a}-${pair.b}`}
                className="border-b last:border-0 hover:bg-muted/30"
              >
                <td className="py-2 text-muted-foreground">{i + 1}</td>
                <td className="py-2 font-medium">{pair.a}</td>
                <td className="py-2 font-medium">{pair.b}</td>
                <td className="py-2 text-right">{pair.count}</td>
                <td className="py-2 text-right">{formatPercent(pair.share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </WidgetWrapper>
  );
}
