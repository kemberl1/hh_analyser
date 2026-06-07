import { useMarketInsight } from "@/api/hooks";
import { WidgetWrapper } from "@/components/WidgetWrapper";
import { useFilters } from "@/context/FilterContext";
import { Bot, Lightbulb, Sparkles, WifiOff } from "lucide-react";

export function MarketInsightWidget() {
  const { filters } = useFilters();
  const { data, isLoading, isError, error, refetch } = useMarketInsight(filters);

  const insight = data?.data;
  const meta = data?.meta;
  const isDisabled = meta?.llm_enabled === false;
  const isEmpty = !insight?.summary || insight.summary.length === 0;

  return (
    <WidgetWrapper
      title="Анализ рынка от ИИ"
      description="LLM-сгенерированные инсайты по данным рынка Frontend"
      isLoading={isLoading}
      isError={isError}
      error={error}
      isEmpty={false}
      onRetry={() => refetch()}
    >
      {isDisabled ? (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <WifiOff className="h-8 w-8 mb-3 text-muted-foreground/60" />
          <p className="text-sm text-center">
            LLM-анализ рынка временно недоступен.
            <br />
            <span className="text-xs">
              Функция отключена или API-ключ не настроен.
            </span>
          </p>
        </div>
      ) : isEmpty ? (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <Bot className="h-8 w-8 mb-3 text-muted-foreground/60" />
          <p className="text-sm">Нет данных для анализа</p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Summary text */}
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <div className="flex items-start gap-2">
              <Sparkles className="h-5 w-5 text-primary mt-0.5 shrink-0" />
              <div className="whitespace-pre-wrap text-sm leading-relaxed">
                {insight?.summary}
              </div>
            </div>
          </div>

          {/* Highlights */}
          {insight?.highlights && insight.highlights.length > 0 && (
            <div className="border-t pt-3">
              <div className="flex items-center gap-1.5 mb-2">
                <Lightbulb className="h-4 w-4 text-yellow-500" />
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Ключевые выводы
                </span>
              </div>
              <ul className="space-y-1">
                {insight.highlights.map((h: string, i: number) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm text-muted-foreground"
                  >
                    <span className="text-primary mt-1">•</span>
                    <span>{h}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Meta info */}
          <div className="border-t pt-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground/70">
            {meta?.model && <span>Модель: {meta.model}</span>}
            {insight?.based_on?.sample_size ? (
              <span>Выборка: {insight.based_on.sample_size} вакансий</span>
            ) : null}
            {meta?.generated_at && (
              <span>
                Сгенерировано:{" "}
                {new Date(meta.generated_at).toLocaleString("ru-RU")}
              </span>
            )}
          </div>
        </div>
      )}
    </WidgetWrapper>
  );
}
