import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AiJobs } from '@recruiter/ui-kit/ai-jobs';

/**
 * 顶部 AI 指令栏把一句话放在路由 state 里带过来。读到后立即从历史记录中清除，
 * 刷新或后退都不会重复发起任务；每条新指令换一个 key，让面板重新执行。
 */
export function AiJobsPage() {
  const loc = useLocation();
  const nav = useNavigate();
  const ask = (loc.state as { ask?: string } | null)?.ask;
  const [command, setCommand] = useState(() => (ask ? { text: ask, id: loc.key } : undefined));
  useEffect(() => {
    if (!ask) return;
    setCommand((c) => (c?.id === loc.key ? c : { text: ask, id: loc.key }));
    nav(loc.pathname + loc.search, { replace: true, state: null });
  }, [ask, loc.key, loc.pathname, loc.search, nav]);
  return <AiJobs key={command?.id ?? 'ai-jobs'} ask={command?.text} />;
}
