import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Toast } from 'antd-mobile';
import { toAppError, useApi, useIdempotencyKey, type WriteOpts } from '@recruiter/api-client';
import { qk } from '@recruiter/domain';

/** 候选人端的写操作：每个操作各自的幂等键，弱网下重复点击不会发两条 */
function useOp<V>(fn: (v: V, opts: WriteOpts) => Promise<unknown>) {
  const qc = useQueryClient();
  const idem = useIdempotencyKey();
  return useMutation({
    mutationFn: (v: V) => fn(v, { idempotencyKey: idem.key() }),
    onSuccess: () => {
      idem.reset();
      void qc.invalidateQueries({ queryKey: ['portal'] });
    },
    onError: (e) => {
      idem.reset();
      Toast.show({ icon: 'fail', content: toAppError(e).message });
    },
  });
}

export function usePortal(token: string) {
  const api = useApi();
  const session = useQuery({ queryKey: qk.candidatePortal.session(), queryFn: () => api.portalSession(token) });
  const granted = session.data?.consent === 'granted';
  // 新消息：SSE 不可用时 3 秒轮询
  const messages = useQuery({ queryKey: qk.candidatePortal.messages(), queryFn: () => api.portalMessages(token), enabled: granted, refetchInterval: 3000 });
  const slots = useQuery({ queryKey: qk.candidatePortal.slots(), queryFn: () => api.portalSlots(token), enabled: granted });

  return {
    session,
    messages,
    slots,
    consent: useOp((v: boolean, o) => api.portalConsent(token, v, o)),
    send: useOp((text: string, o) => api.portalSend(token, text, o)),
    askHuman: useOp((_: void, o) => api.portalAskHuman(token, o)),
    pick: useOp((slotId: string, o) => api.portalPickSlot(token, slotId, o)),
  };
}
