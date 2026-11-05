import { useQuery } from '@tanstack/react-query';
import { useApi } from '@recruiter/api-client';
import { qk } from '@recruiter/domain';
import { useWrite } from '../../shared/useWrite';

export function useRequisitionList() {
  const api = useApi();
  return useQuery({ queryKey: qk.requisition.list(), queryFn: () => api.listRequisitions() });
}

export function usePrecheck(fields: Record<string, string>) {
  const api = useApi();
  const key = JSON.stringify(fields);
  return {
    precheck: useQuery({ queryKey: ['requisition', 'precheck', key], queryFn: () => api.precheckRequisition(fields), placeholderData: (p) => p }),
    chain: useQuery({ queryKey: ['requisition', 'chain', fields.dept, fields.hcRequest], queryFn: () => api.approvalChain(fields), placeholderData: (p) => p }),
  };
}

export function useSubmitRequisition() {
  const api = useApi();
  return useWrite((fields: Record<string, string>, opts) => api.submitRequisition(fields, opts), {
    invalidate: [qk.requisition.list()],
    success: (r) => `已提交 ${r.no}，等${r.waitingFor}审批`,
  });
}
