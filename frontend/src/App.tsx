import { useQuery } from "@tanstack/react-query";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface HealthResponse {
  status: string;
  db: string | null;
}

function App() {
  const { data, isLoading, isError, error } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/api/v1/health`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 10000,
  });

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
      <div className="rounded-lg border bg-card text-card-foreground shadow-sm p-8 max-w-md w-full">
        <h1 className="text-2xl font-bold mb-6 text-center">
          🔍 HH Analyser
        </h1>
        <p className="text-muted-foreground text-center mb-4">
          IT Vacancy Market Analysis
        </p>

        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 rounded-md bg-muted">
            <span className="font-medium">API Status</span>
            {isLoading ? (
              <span className="text-yellow-500">⏳ Checking...</span>
            ) : isError ? (
              <span className="text-red-500">
                ❌ Error: {(error as Error).message}
              </span>
            ) : (
              <span className="text-green-500">✅ {data?.status}</span>
            )}
          </div>

          <div className="flex items-center justify-between p-3 rounded-md bg-muted">
            <span className="font-medium">Database</span>
            {isLoading ? (
              <span className="text-yellow-500">⏳ Checking...</span>
            ) : isError ? (
              <span className="text-red-500">❌ Unknown</span>
            ) : (
              <span
                className={
                  data?.db === "ok" ? "text-green-500" : "text-red-500"
                }
              >
                {data?.db === "ok" ? "✅" : "❌"} {data?.db}
              </span>
            )}
          </div>
        </div>

        <p className="text-xs text-muted-foreground text-center mt-6">
          Backend: {API_URL} • Auto-refresh: 10s
        </p>
      </div>
    </div>
  );
}

export default App;
