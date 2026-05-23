import { Navigate, Route, Routes } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import ExecutiveDashboardPage from "./pages/ExecutiveDashboardPage";
import IntegrationDetailPage from "./pages/IntegrationDetailPage";
import IntegrationsPage from "./pages/IntegrationsPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <div className="app-shell" data-testid="app-shell">
      <NavBar />
      <main className="app-content" data-testid="app-main-content">
        <Routes>
          <Route path="/" element={<ExecutiveDashboardPage />} />
          <Route path="/integrations" element={<IntegrationsPage />} />
          <Route path="/integrations/:integrationId" element={<IntegrationDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
