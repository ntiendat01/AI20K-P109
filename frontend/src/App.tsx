import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import { AppShell } from "./AppShell";
import { LoginPage } from "./LoginPage";
import { DashboardPage, RequestListPage } from "./features/workspace";
import { NewPurchaseRequestPage, PurchaseRequestDetailPage } from "./features/purchaseRequests";
import { QuotationsPage } from "./features/quotations";
import { ComparisonPage } from "./features/comparison";
import { ProcurementWorkflowPage } from "./features/procurementWorkflow";
import { PurchaseOrderPage, PurchaseOrdersPage } from "./features/purchaseOrders";
import { SettingsPage } from "./features/settings";
import { LoadingState } from "./ui";
import { legacyHashToPath } from "./routing";

function ProtectedLayout() {
  const { session, loading } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingState label="Đang khôi phục phiên đăng nhập…" />;
  if (!session) return <Navigate to="/login" replace state={{ from: location }} />;
  return <AppShell />;
}

function RoleRoute({ role, children }: { role: "procurement" | "manager"; children: React.ReactNode }) {
  const { session } = useAuth();
  return session?.user.role === role ? children : <Navigate to="/dashboard" replace />;
}

function LegacyHashRedirect() {
  const navigate = useNavigate();
  useEffect(() => {
    const converted = legacyHashToPath(window.location.hash);
    if (!converted) return;
    history.replaceState(null, "", window.location.pathname);
    navigate(converted, { replace: true });
  }, [navigate]);
  return null;
}

export function App() {
  return <><LegacyHashRedirect /><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<ProtectedLayout />}>
      <Route index element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/requests" element={<RequestListPage />} />
      <Route path="/purchase-requests/new" element={<RoleRoute role="procurement"><NewPurchaseRequestPage /></RoleRoute>} />
      <Route path="/purchase-requests/:requestId/workflow" element={<RoleRoute role="procurement"><ProcurementWorkflowPage /></RoleRoute>} />
      <Route path="/purchase-requests/:requestId/workflow/:stepNumber" element={<RoleRoute role="procurement"><ProcurementWorkflowPage /></RoleRoute>} />
      <Route path="/purchase-requests/:requestId" element={<RoleRoute role="procurement"><PurchaseRequestDetailPage /></RoleRoute>} />
      <Route path="/purchase-requests/:requestId/quotations" element={<RoleRoute role="procurement"><QuotationsPage /></RoleRoute>} />
      <Route path="/purchase-requests/:requestId/comparison" element={<ComparisonPage />} />
      <Route path="/purchase-orders" element={<PurchaseOrdersPage />} />
      <Route path="/purchase-orders/:poId" element={<PurchaseOrderPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Route>
  </Routes></>;
}
