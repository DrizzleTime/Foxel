import { Navigate, Routes, Route, useLocation } from 'react-router';
import type { RouteObject } from 'react-router';
import LayoutShell from './LayoutShell.tsx';
import LoginPage from '../pages/LoginPage.tsx';
import RegisterPage from '../pages/RegisterPage.tsx';
import SetupPage from '../pages/SetupPage.tsx';
import PublicSharePage from '../pages/PublicSharePage';
import ForgotPasswordPage from '../pages/ForgotPasswordPage';
import ResetPasswordPage from '../pages/ResetPasswordPage';
import { useAuth } from '../contexts/AuthContext';
import type { JSX } from 'react';

export const routes: RouteObject[] = [
  { path: '/', element: <Navigate to="/files" replace /> },
  { path: '/:navKey/*', element: <LayoutShell /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  { path: '/share/:token', element: <PublicSharePage /> },
  { path: '/setup', element: <SetupPage /> },
  { path: '/forgot-password', element: <ForgotPasswordPage /> },
  { path: '/reset-password', element: <ResetPasswordPage /> },
];

function RequireAuth({ children }: { children: JSX.Element }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  const publicPaths = ['/login', '/register', '/forgot-password', '/reset-password'];
  const isPublic = publicPaths.some((p) => location.pathname.startsWith(p));
  if (!isAuthenticated && !location.pathname.startsWith('/share/') && !isPublic) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export function AppRouter() {
  return (
    <RequireAuth>
      <Routes>
        {routes.map(r => (
          <Route key={r.path} path={r.path} element={r.element} />
        ))}
      </Routes>
    </RequireAuth>
  );
}

export default AppRouter;
