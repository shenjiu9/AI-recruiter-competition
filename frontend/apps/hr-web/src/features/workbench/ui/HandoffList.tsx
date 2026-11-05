import { Button, List } from 'antd';
import { Link } from 'react-router-dom';
import { formatDue, type Handoff } from '@recruiter/domain';
import { EmptyState } from '@recruiter/ui-kit';

export function HandoffList({ items }: { items: Handoff[] }) {
  if (!items.length) return <EmptyState title="没有转给你的会话" why="候选人要求人工、问到知识库没有的内容或话题敏感时，会话会转到这里。" />;
  return (
    <List
      className="panel"
      dataSource={items}
      renderItem={(h) => {
        const due = formatDue(h.dueAt);
        return (
          <List.Item style={{ padding: '14px 16px' }} actions={[<Link key="go" to={`/candidates/${h.candidateId}?tab=conversation`}><Button type="primary" size="small">去回复</Button></Link>]}>
            <List.Item.Meta
              title={<span>{h.candidateName}<span className="muted" style={{ marginLeft: 12, fontWeight: 400, fontSize: 12 }}>{h.positionName}</span></span>}
              description={
                <>
                  <div>原因：{h.reason}</div>
                  <div className="muted">最后一条：{h.lastMessage}</div>
                </>
              }
            />
            <span style={{ fontSize: 12, color: due.urgent ? 'var(--rc-warn)' : 'var(--rc-ink-3)' }}>请在 {due.text} 前回复</span>
          </List.Item>
        );
      }}
    />
  );
}
