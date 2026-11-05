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
  return useWrite(
    async (v: { id: string; action: string; version?: number; nodeId?: string }, opts) => {
      if (v.version !== undefined && v.nodeId) {
        await api.approveRequisition(v.id, v.nodeId, v.version, opts);
        return;
      }
      await api.bizAct(v.id, v.action, opts);
    },
    { invalidate: [qk.biz.inbox()] },
  );
}
