import { useQuery } from '@tanstack/react-query';
import { useApi } from '@recruiter/api-client';
import { qk, type Position } from '@recruiter/domain';
import { useWrite } from '../../shared/useWrite';

export function usePositionList() {
  const api = useApi();
  return useQuery({ queryKey: qk.position.list(), queryFn: () => api.listPositions() });
}

export function usePositionDetail(id: string) {
  const api = useApi();
  return {
    position: useQuery({ queryKey: qk.position.detail(id), queryFn: () => api.getPosition(id) }),
    funnel: useQuery({ queryKey: qk.position.funnel(id), queryFn: () => api.positionFunnel(id) }),
    applications: useQuery({ queryKey: qk.position.applications(id), queryFn: () => api.positionApplications(id) }),
    profile: useQuery({ queryKey: qk.position.profile(id), queryFn: () => api.getProfile(id) }),
    kb: useQuery({ queryKey: qk.position.kb(id), queryFn: () => api.listKb(id) }),
  };
}

export function useTransitionPosition(p: Position | undefined) {
  const api = useApi();
  const labels = { pause: '已暂停，渠道展示与主动触达已停止', resume: '已恢复招聘', close: '已关闭岗位，各渠道将在 10 分钟内下线' } as const;
  return useWrite((action: 'pause' | 'resume' | 'close', opts) => api.transitionPosition(p!.id, action, p!.version, opts), {
    invalidate: [qk.position.detail(p?.id ?? ''), qk.position.list()],
    success: (r) => labels[r.status === 'paused' ? 'pause' : r.status === 'open' ? 'resume' : 'close'],
  });
}
