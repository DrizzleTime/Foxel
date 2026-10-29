import { Navigate, Routes, Route, useLocation } from 'react-router';
import type { RouteObject } from 'react-router';
import { lazy, Suspense } from 'react';
import LoginPage from '../pages/LoginPage.tsx';
import PageLoading from '../components/PageLoading';
import { useAuth } from '../contexts/AuthContext';
import type { JSX } from 'react';

const LayoutShell = lazy(() => import('./LayoutShell.tsx'));
const RegisterPage = lazy(() => import('../pages/RegisterPage.tsx'));
const SetupPage = lazy(() => import('../pages/SetupPage.tsx'));
const PublicSharePage = lazy(() => import('../pages/PublicSharePage'));
const VideoRoomPage = lazy(() => import('../pages/VideoRoomPage'));
const ForgotPasswordPage = lazy(() => import('../pages/ForgotPasswordPage'));
const ResetPasswordPage = lazy(() => import('../pages/ResetPasswordPage'));

export const routes: RouteObject[] = [
  { path: '/', element: <Navigate to="/files" replace /> },
  { path: '/settings/*', element: <Navigate to="/files" replace /> },
  { path: '/:navKey/*', element: <LayoutShell /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  { path: '/share/:token', element: <PublicSharePage /> },
  { path: '/room/:token', element: <VideoRoomPage /> },
  { path: '/setup', element: <SetupPage /> },
  { path: '/forgot-password', element: <ForgotPasswordPage /> },
  { path: '/reset-password', element: <ResetPasswordPage /> },
];

function RequireAuth({ children }: { children: JSX.Element }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  const publicPaths = ['/login', '/register', '/forgot-password', '/reset-password'];
  const isPublic = publicPaths.some((p) => location.pathname.startsWith(p));
  if (!isAuthenticated && !location.pathname.startsWith('/share/') && !location.pathname.startsWith('/room/') && !isPublic) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export function AppRouter() {
  return (
    <RequireAuth>
      <Suspense fallback={<PageLoading fullPage />}>
        <Routes>
          {routes.map(r => (
            <Route
              key={r.path}
              path={r.path}
              element={r.element}
            />
          ))}
        </Routes>
      </Suspense>
    </RequireAuth>
  );
}

export default AppRouter;
