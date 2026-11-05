import { useQuery } from '@tanstack/react-query';
import { useApi, type CardResolution } from '@recruiter/api-client';
import { qk } from '@recruiter/domain';
import { useWrite } from '../../shared/useWrite';

export function useWorkbench() {
  const api = useApi();
  return {
    summary: useQuery({ queryKey: qk.workbench.summary(), queryFn: () => api.workbenchSummary() }),
    cards: useQuery({ queryKey: qk.workbench.cards(), queryFn: () => api.listOpenCards() }),
    activity: useQuery({ queryKey: qk.workbench.activity(), queryFn: () => api.aiActivity() }),
    health: useQuery({ queryKey: qk.workbench.health(), queryFn: () => api.positionHealth() }),
    handoffs: useQuery({ queryKey: qk.workbench.handoffs(), queryFn: () => api.handoffs() }),
    anomalies: useQuery({ queryKey: qk.workbench.anomalies(), queryFn: () => api.anomalies() }),
  };
}

export function useResolveCard() {
  const api = useApi();
  return useWrite((v: { id: string; body: CardResolution }, opts) => api.resolveCard(v.id, v.body, opts), {
    invalidate: [qk.workbench.summary()],
  });
}

export function useUndoAction() {
  const api = useApi();
  return useWrite((id: string, opts) => api.undoAction(id, opts), { invalidate: [qk.workbench.activity()], success: '已撤销，对象已恢复到动作前的状态' });
}

export function useCorrectAction() {
  const api = useApi();
  return useWrite((v: { id: string; note: string }, opts) => api.correctAction(v.id, v.note, opts), {
    invalidate: [qk.workbench.activity()],
    success: '已标记纠正，AI 会生成补救建议',
  });
}
