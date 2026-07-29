import { Navigate, Route, Routes } from "react-router-dom";

import MainLayout from "./layouts/MainLayout";
import DashboardPage from "./pages/DashboardPage";
import DocumentsPage from "./pages/DocumentsPage";
import DraftDetailPage from "./pages/DraftDetailPage";
import DraftHistoryPage from "./pages/DraftHistoryPage";
import LoginPage from "./pages/LoginPage";
import MailboxesPage from "./pages/MailboxesPage";
import PromptsPage from "./pages/PromptsPage";
import SimulatorPage from "./pages/SimulatorPage";
import ProtectedRoute from "./routes/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<MainLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/mailboxes" element={<MailboxesPage />} />
          <Route path="/prompts" element={<PromptsPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/drafts" element={<DraftHistoryPage />} />
          <Route path="/drafts/:emailMessageId" element={<DraftDetailPage />} />
          <Route path="/simulator" element={<SimulatorPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
