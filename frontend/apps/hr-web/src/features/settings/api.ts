import { useQuery } from '@tanstack/react-query';
import { useApi } from '@recruiter/api-client';
import { qk, type Level } from '@recruiter/domain';
import { useWrite } from '../../shared/useWrite';

export function useAutomation() {
  const api = useApi();
  const nodes = useQuery({ queryKey: qk.settings.automation(), queryFn: () => api.automationNodes() });
  const setLevel = useWrite((v: { key: string; level: Level }, opts) => api.setAutomationLevel(v.key, v.level, opts), {
    invalidate: [qk.settings.automation()],
    success: (n) => `${n.name}已改为 L${n.level}`,
  });
  return { nodes, setLevel };
}
