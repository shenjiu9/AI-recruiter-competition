import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { ApiProvider, type ApiConfig } from '@recruiter/api-client';
import { AuthProvider, SessionGate } from '@recruiter/auth';
import { useState } from 'react';
import '@recruiter/mobile-ui';
import { InboxPage } from '../pages/InboxPage';
import { BriefPage } from '../pages/BriefPage';
import { FeedbackPage } from '../pages/FeedbackPage';

const apiConfig: ApiConfig = {
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
  mock: import.meta.env.VITE_USE_MOCK !== 'false',
};

const router = createBrowserRouter([
  { path: '/', element: <InboxPage /> },
  { path: '/brief/:appId', element: <BriefPage /> },
  { path: '/feedback/:appId', element: <FeedbackPage /> },
]);

/** 飞书内 H5：业务方只看需要他决定的事，30 秒内完成一个决定 */
function AuthenticatedApp() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } }),
  );
  return (
    <ApiProvider config={apiConfig}>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ApiProvider>
  );
}

export function App() {
  return (
    <AuthProvider
      mockSession={
        apiConfig.mock
          ? {
              userId: 'u-zhouzh',
              name: '周振华',
              roles: ['hiring_manager', 'interviewer'],
              token: 'demo',
            }
          : undefined
      }
    >
      <SessionGate mock={apiConfig.mock} baseUrl={apiConfig.baseUrl}>
        <AuthenticatedApp />
      </SessionGate>
    </AuthProvider>
  );
}
