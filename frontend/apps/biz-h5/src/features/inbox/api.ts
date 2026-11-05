import { useQuery } from '@tanstack/react-query';
import { useApi } from '@recruiter/api-client';
import { qk } from '@recruiter/domain';
import { useWrite } from '../../shared/useWrite';

export function useInbox() {
  const api = useApi();
  return useQuery({ queryKey: qk.biz.inbox(), queryFn: () => api.bizInbox() });
}

export function useInboxAct() {
  const api = useApi();
  return useWrite((v: { id: string; action: string }, opts) => api.bizAct(v.id, v.action, opts), { invalidate: [qk.biz.inbox()] });
}
