import type {
    Currency,
    Grade,
    MetricFilters,
    Period,
    SalaryBasis,
} from "@/api/types";
import {
    createContext,
    useCallback,
    useContext,
    useMemo,
    useState,
    type ReactNode,
} from "react";

interface FilterState {
  period: Period;
  grade: Grade;
  currency: Currency;
  salary_basis: SalaryBasis;
  date_from?: string;
  date_to?: string;
}

interface FilterContextValue {
  filters: MetricFilters;
  state: FilterState;
  setPeriod: (p: Period) => void;
  setGrade: (g: Grade) => void;
  setCurrency: (c: Currency) => void;
  setSalaryBasis: (s: SalaryBasis) => void;
  setDateRange: (from?: string, to?: string) => void;
}

const FilterContext = createContext<FilterContextValue | null>(null);

export function FilterProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FilterState>({
    period: "month",
    grade: "all",
    currency: "RUB",
    salary_basis: "net",
  });

  const setPeriod = useCallback(
    (period: Period) => setState((s) => ({ ...s, period })),
    []
  );
  const setGrade = useCallback(
    (grade: Grade) => setState((s) => ({ ...s, grade })),
    []
  );
  const setCurrency = useCallback(
    (currency: Currency) => setState((s) => ({ ...s, currency })),
    []
  );
  const setSalaryBasis = useCallback(
    (salary_basis: SalaryBasis) => setState((s) => ({ ...s, salary_basis })),
    []
  );
  const setDateRange = useCallback(
    (date_from?: string, date_to?: string) =>
      setState((s) => ({ ...s, date_from, date_to })),
    []
  );

  const filters: MetricFilters = useMemo(
    () => ({
      period: state.period,
      grade: state.grade,
      currency: state.currency,
      salary_basis: state.salary_basis,
      date_from: state.date_from,
      date_to: state.date_to,
    }),
    [state]
  );

  const value = useMemo(
    () => ({
      filters,
      state,
      setPeriod,
      setGrade,
      setCurrency,
      setSalaryBasis,
      setDateRange,
    }),
    [filters, state, setPeriod, setGrade, setCurrency, setSalaryBasis, setDateRange]
  );

  return (
    <FilterContext.Provider value={value}>{children}</FilterContext.Provider>
  );
}

export function useFilters(): FilterContextValue {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error("useFilters must be used within FilterProvider");
  return ctx;
}
