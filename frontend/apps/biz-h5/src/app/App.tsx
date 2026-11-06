import { BusinessShell } from './BusinessShell';
import { RecruiterTheme } from '@recruiter/ui-kit/theme';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { ApiProvider, type ApiConfig } from '@recruiter/api-client';
import { AuthProvider, SessionGate } from '@recruiter/auth';
import { useState } from 'react';
import '@recruiter/mobile-ui';
import { InboxPage } from '../pages/InboxPage';
import { BriefPage } from '../pages/BriefPage';
import { FeedbackPage } from '../pages/FeedbackPage';
import { PositionsPage, PositionReviewPage } from '../pages/PositionsPage';
import { InterviewsPage, InterviewPage } from '../pages/InterviewsPage';
import { HiringPage, WorkbenchPage } from '../pages/HiringPage';
import { AiJobs } from '@recruiter/ui-kit/ai-jobs';

const apiConfig: ApiConfig = {
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
  mock: import.meta.env.VITE_USE_MOCK !== 'false',
};

const router = createBrowserRouter([
  {
    element: <BusinessShell />,
    children: [
      { path: '/', element: <InboxPage /> },
      { path: '/brief/:appId', element: <BriefPage /> },
      { path: '/feedback/:appId', element: <FeedbackPage /> },
      { path: '/positions', element: <PositionsPage /> },
      { path: '/interviews', element: <InterviewsPage /> },
      { path: '/hiring', element: <HiringPage /> },
      { path: '/hiring/:id', element: <HiringPage /> },
      { path: '/workbench', element: <WorkbenchPage /> },
      { path: '/ai-jobs', element: <AiJobs business /> },
      { path: '/interviews/:id', element: <InterviewPage /> },
      { path: '/positions/:id', element: <PositionReviewPage /> },
    ],
  },
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
    <RecruiterTheme>
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
    </RecruiterTheme>
  );
}
