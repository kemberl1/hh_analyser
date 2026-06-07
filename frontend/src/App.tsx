import { Dashboard } from "@/components/Dashboard";
import { FilterProvider } from "@/context/FilterContext";

function App() {
  return (
    <FilterProvider>
      <Dashboard />
    </FilterProvider>
  );
}

export default App;
