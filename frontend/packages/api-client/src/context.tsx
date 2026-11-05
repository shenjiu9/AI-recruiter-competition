import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { ApiClient, ApiConfig } from './client';
import { createHttpClient } from './http';
import { createMockClient } from './mock/server';

export function createApiClient(config: ApiConfig): ApiClient {
  return config.mock ? createMockClient() : createHttpClient(config);
}

const ApiContext = createContext<ApiClient | null>(null);

export function ApiProvider({ config, children }: { config: ApiConfig; children: ReactNode }) {
  const client = useMemo(() => createApiClient(config), [config]);
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiClient {
  const c = useContext(ApiContext);
  if (!c) throw new Error('useApi 必须在 ApiProvider 内使用');
  return c;
}
