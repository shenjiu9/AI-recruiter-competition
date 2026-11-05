import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider, type ApiConfig } from '@recruiter/api-client';
import { AuthProvider } from '@recruiter/auth';
import { PortalPage } from '../pages/PortalPage';

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: 1 } } });
const apiConfig: ApiConfig = { baseUrl: import.meta.env.VITE_API_BASE_URL ?? '', mock: import.meta.env.VITE_USE_MOCK !== 'false' };

/** 候选人端：手机 H5（含微信内置浏览器），签名链接免注册 */
export function App() {
  return (
    <AuthProvider>
      <ApiProvider config={apiConfig}>
        <QueryClientProvider client={queryClient}>
          <PortalPage />
        </QueryClientProvider>
      </ApiProvider>
    </AuthProvider>
  );
}
