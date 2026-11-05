import '../shared/global.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { ApiProvider, type ApiConfig } from '@recruiter/api-client';
import { AuthProvider, SessionGate, type Session } from '@recruiter/auth';
import { useState } from 'react';
import { RecruiterTheme } from '@recruiter/ui-kit';
import { router } from './routes';

function AuthenticatedApp() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
      }),
  );
  return (
    <ApiProvider config={apiConfig}>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ApiProvider>
  );
}

const apiConfig: ApiConfig = {
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
  mock: import.meta.env.VITE_USE_MOCK !== 'false',
};

const demoSession: Session = {
  userId: 'u-linyue',
  name: '林悦',
  roles: ['recruiter', 'recruiting_lead'],
  token: 'demo',
};

export function App() {
  return (
    <RecruiterTheme>
      <AuthProvider
        mockSession={apiConfig.mock ? demoSession : undefined}
        feishuAuthUrl="/api/v1/auth/feishu"
      >
        <SessionGate mock={apiConfig.mock} baseUrl={apiConfig.baseUrl}>
          <AuthenticatedApp />
        </SessionGate>
      </AuthProvider>
    </RecruiterTheme>
  );
}
