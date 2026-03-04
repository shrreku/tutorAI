import { Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MainLayout } from './components/layout';
import { useAuth } from './hooks/useAuth';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import HomePage from './pages/HomePage';
import BillingPage from './pages/BillingPage';
import SettingsPage from './pages/SettingsPage';
import NotebooksPage from './pages/NotebooksPage';
import NotebookCreatePage from './pages/NotebookCreatePage';
import NotebookDetailPage from './pages/NotebookDetailPage';
import NotebookStudyPage from './pages/NotebookStudyPage';
import NotebookResourcesPage from './pages/NotebookResourcesPage';
import NotebookSessionsPage from './pages/NotebookSessionsPage';
import NotebookProgressArtifactsPage from './pages/NotebookProgressArtifactsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: 1,
    },
  },
});

/** Redirect to landing if not authenticated. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/landing" replace />;
  return <>{children}</>;
}

/** Redirect to dashboard if already authenticated. */
function GuestOnly({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function App() {
  const notebooksEnabled = import.meta.env.VITE_FEATURE_NOTEBOOKS_ENABLED !== 'false';

  return (
    <QueryClientProvider client={queryClient}>
      <Routes>
        {/* ── Public / guest routes ─────────────────── */}
        <Route path="/landing" element={<GuestOnly><LandingPage /></GuestOnly>} />
        <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
        <Route path="/register" element={<GuestOnly><RegisterPage /></GuestOnly>} />

        {/* ── Authenticated app routes ──────────────── */}
        <Route element={<RequireAuth><MainLayout /></RequireAuth>}>
          <Route path="/" element={<HomePage />} />
          {notebooksEnabled && <Route path="/notebooks" element={<NotebooksPage />} />}
          {notebooksEnabled && <Route path="/notebooks/new" element={<NotebookCreatePage />} />}
          {notebooksEnabled && <Route path="/notebooks/:notebookId" element={<NotebookDetailPage />} />}
          {notebooksEnabled && <Route path="/notebooks/:notebookId/study" element={<NotebookStudyPage />} />}
          {notebooksEnabled && <Route path="/notebooks/:notebookId/resources" element={<NotebookResourcesPage />} />}
          {notebooksEnabled && <Route path="/notebooks/:notebookId/sessions" element={<NotebookSessionsPage />} />}
          {notebooksEnabled && <Route path="/notebooks/:notebookId/progress" element={<NotebookProgressArtifactsPage />} />}
          <Route path="/resources" element={<Navigate to="/notebooks" replace />} />
          <Route path="/resources/:id" element={<Navigate to="/notebooks" replace />} />
          <Route path="/sessions" element={<Navigate to="/notebooks" replace />} />
          <Route path="/sessions/new" element={<Navigate to="/notebooks" replace />} />
          <Route path="/sessions/:id" element={<Navigate to="/notebooks" replace />} />
          <Route path="/sessions/:sessionId/quiz" element={<Navigate to="/notebooks" replace />} />
          <Route path="/billing" element={<BillingPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        {/* ── Fallback ──────────────────────────────── */}
        <Route path="*" element={<Navigate to="/landing" replace />} />
      </Routes>
    </QueryClientProvider>
  );
}

export default App;
