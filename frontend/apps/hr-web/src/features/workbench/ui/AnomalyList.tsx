import { List } from 'antd';
import { Link } from 'react-router-dom';
import type { Anomaly } from '@recruiter/domain';
import { EmptyState } from '@recruiter/ui-kit';

export function AnomalyList({ items }: { items: Anomaly[] }) {
  if (!items.length) return <EmptyState title="一切正常" why="面评超时、审批卡住、渠道账号失效或 AI 执行失败时会出现在这里。" />;
  return (
    <List
      className="panel"
      dataSource={items}
      renderItem={(a) => (
        <List.Item style={{ padding: '14px 16px' }} actions={a.link ? [<Link key="go" to={a.link}>去处理</Link>] : []}>
          <List.Item.Meta title={a.kind} description={a.text} />
        </List.Item>
      )}
    />
  );
}
