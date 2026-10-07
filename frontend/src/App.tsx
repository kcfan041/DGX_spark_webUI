import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "@/auth/RequireAuth";
import { AppLayout } from "@/layout/AppLayout";
import { CloudPage } from "@/pages/CloudPage";
import { UsagePage } from "@/pages/UsagePage";
import { CreateServicePage } from "@/pages/CreateServicePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { GatewayPage } from "@/pages/GatewayPage";
import { LogsPage } from "@/pages/LogsPage";
import { ServiceDetailPage } from "@/pages/ServiceDetailPage";
import { LoginPage } from "@/pages/LoginPage";
import { ModelsPage } from "@/pages/ModelsPage";
import { ServicesPage } from "@/pages/ServicesPage";
import { SettingsPage } from "@/pages/SettingsPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/services/new" element={<CreateServicePage />} />
        <Route path="/services/:id" element={<ServiceDetailPage />} />
        <Route path="/gateway" element={<GatewayPage />} />
        <Route path="/cloud" element={<CloudPage />} />
        <Route path="/usage" element={<UsagePage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
