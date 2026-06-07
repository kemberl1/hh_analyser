/**
 * Format a number as a salary string with thousands separator.
 * E.g., 220000 → "220 000 ₽"
 */
export function formatSalary(
  value: number | null | undefined,
  currency = "RUB"
): string {
  if (value == null) return "—";
  const symbol = currencySymbol(currency);
  return `${value.toLocaleString("ru-RU")} ${symbol}`;
}

export function currencySymbol(currency: string): string {
  switch (currency.toUpperCase()) {
    case "RUB":
      return "₽";
    case "USD":
      return "$";
    case "EUR":
      return "€";
    default:
      return currency;
  }
}

/** Format percentage 0.62 → "62%" */
export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

/** Format growth +0.04 → "+4.0%" */
export function formatGrowth(value: number | null | undefined): string {
  if (value == null) return "—";
  const pct = (value * 100).toFixed(1);
  return value >= 0 ? `+${pct}%` : `${pct}%`;
}

/** Format number with space separator */
export function formatNumber(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString("ru-RU");
}

/** Format hours to human readable "X ч назад" / "X д назад" */
export function formatFreshness(hours: number | null | undefined): string {
  if (hours == null) return "Нет данных";
  if (hours < 1) return "< 1 ч назад";
  if (hours < 24) return `${Math.round(hours)} ч назад`;
  const days = Math.floor(hours / 24);
  return `${days} д назад`;
}

/** Short period_start date label */
export function formatPeriodLabel(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString("ru-RU", { month: "short", day: "numeric" });
}

/** Grade label mapping */
export function gradeLabel(grade: string): string {
  switch (grade) {
    case "junior":
      return "Junior";
    case "middle":
      return "Middle";
    case "senior":
      return "Senior";
    case "all":
      return "Все грейды";
    default:
      return grade;
  }
}

/** Period label mapping */
export function periodLabel(period: string): string {
  switch (period) {
    case "day":
      return "День";
    case "week":
      return "Неделя";
    case "month":
      return "Месяц";
    case "year":
      return "Год";
    default:
      return period;
  }
}
