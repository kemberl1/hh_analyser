import { Dashboard } from "@/components/Dashboard";
import { ResumeAnalyzer } from "@/components/ResumeAnalyzer";
import { FilterProvider } from "@/context/FilterContext";
import { BarChart3, FileSearch } from "lucide-react";
import { useState } from "react";

type Tab = "dashboard" | "resume";

function App() {
  const [tab, setTab] = useState<Tab>("dashboard");

  return (
    <FilterProvider>
      {/* Global nav tabs */}
      <div className="sticky top-0 z-[60] bg-background border-b">
        <div className="container mx-auto px-4">
          <nav className="flex gap-1 py-1">
            <button
              onClick={() => setTab("dashboard")}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                tab === "dashboard"
                  ? "bg-primary/10 text-primary border-b-2 border-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
              }`}
            >
              <BarChart3 className="h-4 w-4" />
              Дашборд
            </button>
            <button
              onClick={() => setTab("resume")}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                tab === "resume"
                  ? "bg-primary/10 text-primary border-b-2 border-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
              }`}
            >
              <FileSearch className="h-4 w-4" />
              Анализатор резюме
            </button>
          </nav>
        </div>
      </div>

      {tab === "dashboard" && <Dashboard />}
      {tab === "resume" && <ResumeAnalyzer />}
    </FilterProvider>
  );
}

export default App;
