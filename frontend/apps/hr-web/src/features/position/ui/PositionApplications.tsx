import { Table } from 'antd';
import { Link } from 'react-router-dom';
import type { Application } from '@recruiter/domain';
import { ConfidenceTag, StageBadge } from '@recruiter/ui-kit';

type Row = Application & { candidateName: string; confidence?: number };

export function PositionApplications({ rows, loading }: { rows: Row[]; loading: boolean }) {
  return (
    <Table<Row>
      rowKey="id"
      size="middle"
      loading={loading}
      dataSource={rows}
      pagination={false}
      locale={{ emptyText: '这个岗位还没有候选人。发布后 AI 会开始触达，也可以从人才库挂人。' }}
      columns={[
        { title: '候选人', render: (_, r) => <Link to={`/candidates/${r.candidateId}`} style={{ fontWeight: 500 }}>{r.candidateName}</Link> },
        { title: '阶段', render: (_, r) => <StageBadge stage={r.stage} ended={r.ended?.result} /> },
        { title: '状态', dataIndex: 'subStatus' },
        { title: 'AI 把握', render: (_, r) => (r.confidence !== undefined ? <ConfidenceTag value={r.confidence} /> : <span className="muted">未评估</span>) },
        { title: '来源', dataIndex: 'source' },
      ]}
    />
  );
}
