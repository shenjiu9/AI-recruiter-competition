import { useQuery } from '@tanstack/react-query';
import { useApi } from '@recruiter/api-client';
import { qk } from '@recruiter/domain';
import { useWrite } from '../../shared/useWrite';

export function useCandidateDetail(id: string, applicationId?: string) {
  const api = useApi();
  const candidate = useQuery({ queryKey: qk.candidate.detail(id), queryFn: () => api.getCandidate(id) });
  const applications = useQuery({ queryKey: qk.candidate.applications(id), queryFn: () => api.listApplications(id) });
  const appId = applicationId ?? applications.data?.find((a) => !a.ended)?.id ?? applications.data?.[0]?.id;
  const evaluation = useQuery({ queryKey: qk.evaluation(appId ?? ''), queryFn: () => api.getEvaluation(appId!), enabled: !!appId });
  const resume = useQuery({ queryKey: qk.candidate.resume(id), queryFn: () => api.getResume(id) });
  const conversation = useQuery({ queryKey: qk.candidate.conversation(id), queryFn: () => api.getConversation(id) });
  const logs = useQuery({ queryKey: qk.candidate.logs(id), queryFn: () => api.operationLogs(id) });
  return { candidate, applications, evaluation, resume, conversation, logs, appId };
}

export function useConversationActions(id: string) {
  const api = useApi();
  const inv = { invalidate: [qk.candidate.conversation(id), qk.workbench.handoffs()] };
  return {
    takeOver: useWrite((_: void, opts) => api.takeOver(id, opts), { ...inv, success: '已接管会话，AI 停止自动发送' }),
    handBack: useWrite((_: void, opts) => api.handBack(id, opts), { ...inv, success: '已交还 AI' }),
    send: useWrite((text: string, opts) => api.sendAsHr(id, text, opts), { ...inv, success: '已发送' }),
  };
}

export function useCandidateList(q?: string) {
  const api = useApi();
  return useQuery({ queryKey: qk.candidate.list({ q }), queryFn: () => api.listCandidates(q) });
}
