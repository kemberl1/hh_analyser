import { DashboardHeader } from "@/components/DashboardHeader";
import { CooccurrenceWidget } from "@/components/widgets/CooccurrenceWidget";
import { DemandWidget } from "@/components/widgets/DemandWidget";
import { DistributionWidget } from "@/components/widgets/DistributionWidget";
import { EmployersWidget } from "@/components/widgets/EmployersWidget";
import { OverviewKPI } from "@/components/widgets/OverviewKPI";
import { SalaryTimeseriesWidget } from "@/components/widgets/SalaryTimeseriesWidget";
import { SalaryWidget } from "@/components/widgets/SalaryWidget";
import { SkillsWidget } from "@/components/widgets/SkillsWidget";

export function Dashboard() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <DashboardHeader />

      <main className="container mx-auto px-4 py-6 space-y-6">
        {/* KPI cards row */}
        <section>
          <OverviewKPI />
        </section>

        {/* Salary + Timeseries row */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <SalaryWidget />
          <SalaryTimeseriesWidget />
        </section>

        {/* Demand + Distribution row */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <DemandWidget />
          <DistributionWidget />
        </section>

        {/* Skills + Co-occurrence row */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <SkillsWidget />
          <CooccurrenceWidget />
        </section>

        {/* Employers — full width */}
        <section>
          <EmployersWidget />
        </section>
      </main>

      <footer className="border-t py-4 text-center text-xs text-muted-foreground">
        HH Analyser • Frontend Vacancy Market Analysis •{" "}
        {new Date().getFullYear()}
      </footer>
    </div>
  );
}
