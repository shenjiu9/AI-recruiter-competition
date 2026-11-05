import { useQuery } from '@tanstack/react-query';
import { useApi, type RequisitionDetail } from '@recruiter/api-client';
import { qk } from '@recruiter/domain';
import { useWrite } from '../../shared/useWrite';

export function useRequisitionList(page = 1, size = 20) {
  const api = useApi();
  return useQuery({
    queryKey: [...qk.requisition.list(), page, size],
    queryFn: () => api.requisitionPage(page, size),
  });
}

export function usePrecheck(fields: Record<string, string>) {
  const api = useApi();
  const key = JSON.stringify(fields);
  return {
    precheck: useQuery({
      queryKey: ['requisition', 'precheck', key],
      queryFn: () => api.precheckRequisition(fields),
      placeholderData: (p) => p,
    }),
    chain: useQuery({
      queryKey: ['requisition', 'chain', key],
      queryFn: () => api.approvalChain(fields),
      placeholderData: (p) => p,
    }),
  };
}

export function useSubmitRequisition(initial?: RequisitionDetail) {
  const api = useApi();
  return useWrite(
    (fields: Record<string, string>, opts) =>
      initial
        ? api.submitRequisitionDraft(initial.id, fields, initial.version, opts)
        : api.submitRequisition(fields, opts),
    {
      invalidate: [qk.requisition.list(), ['requisition', 'detail']],
      success: (r) => `已提交 ${r.no}，等${r.waitingFor}审批`,
    },
  );
}

export function useSaveRequisition(initial?: RequisitionDetail) {
  const api = useApi();
  return useWrite(
    (fields: Record<string, string>, opts) =>
      initial
        ? api.updateRequisitionDraft(initial.id, fields, initial.version, opts)
        : api.createRequisitionDraft(fields, opts),
    {
      invalidate: [qk.requisition.list(), ['requisition', 'detail']],
      success: '草稿已保存',
    },
  );
}

export function useRequisitionDetail(id: string) {
  const api = useApi();
  return useQuery({
    queryKey: ['requisition', 'detail', id],
    queryFn: () => api.getRequisition(id),
    enabled: !!id,
  });
}

export function useRequisitionAction(req: RequisitionDetail | undefined) {
  const api = useApi();
  return useWrite(
    ({ action, reason }: { action: 'approve' | 'reject' | 'withdraw'; reason?: string }, opts) => {
      if (!req) throw new Error('需求尚未加载');
      const node = req.chain[req.currentNode];
      if (action === 'withdraw') return api.withdrawRequisition(req.id, req.version, opts);
      if (action === 'reject')
        return api.rejectRequisition(req.id, node!.id, req.version, reason ?? '', opts);
      return api.approveRequisition(req.id, node!.id, req.version, opts);
    },
    { invalidate: [qk.requisition.list(), ['requisition', 'detail']], success: '已处理' },
  );
}
