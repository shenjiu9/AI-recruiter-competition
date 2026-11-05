import { Link } from 'react-router-dom';
import { EmptyState } from '@recruiter/ui-kit';

export function PlaceholderPage({ title, phase }: { title: string; phase?: string }) {
  return (
    <EmptyState
      title={title}
      why={phase ? `这个模块计划在${phase}上线，MVP 暂不包含。` : '你访问的地址不存在，可能链接已过期。'}
      action={<Link to="/workbench">回到工作台</Link>}
    />
  );
}
