import { Table } from 'antd';
import { Link } from 'react-router-dom';
import { POSITION_STATUS_LABEL, formatDate, type Position } from '@recruiter/domain';
import { HealthTag } from '@recruiter/ui-kit';

const POSITION_TONE = { to_publish: 'muted', open: 'active', paused: 'warn', closed: 'muted' } as const;

export function PositionTable({ rows, loading }: { rows: Position[]; loading: boolean }) {
  return (
    <Table<Position>
      rowKey="id"
      loading={loading}
      dataSource={rows}
      pagination={false}
      columns={[
        {
          title: '岗位',
          render: (_, p) => (
            <div>
              <Link to={`/positions/${p.id}`} style={{ fontWeight: 500 }}>
                {p.name}
              </Link>
              <div className="muted" style={{ fontSize: 12 }}>
                {p.dept} {p.city} {p.id}
              </div>
            </div>
          ),
        },
        {
          title: '状态',
          width: 100,
          render: (_, p) => (
            <span className="rc-status" data-tone={POSITION_TONE[p.status]}>
              {POSITION_STATUS_LABEL[p.status]}
            </span>
          ),
        },
        {
          title: '可招',
          align: 'right',
          width: 90,
          render: (_, p) => (
            <span className="num">
              {p.planned - p.hired} / {p.planned}
            </span>
          ),
        },
        { title: '健康度', width: 90, render: (_, p) => <HealthTag level={p.health} /> },
        { title: '负责 HR', dataIndex: 'ownerHr', width: 90 },
        {
          title: '期望到岗',
          width: 120,
          render: (_, p) => <span className="num rc-nowrap">{formatDate(p.expectedOnboard)}</span>,
        },
      ]}
    />
  );
}
