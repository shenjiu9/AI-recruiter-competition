import { Table } from 'antd';
import { Link } from 'react-router-dom';
import { POSITION_STATUS_LABEL, formatDate, type Position } from '@recruiter/domain';
import { HealthTag } from '@recruiter/ui-kit';

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
        { title: '状态', render: (_, p) => POSITION_STATUS_LABEL[p.status], width: 90 },
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
          width: 110,
          render: (_, p) => <span className="num">{formatDate(p.expectedOnboard)}</span>,
        },
      ]}
    />
  );
}
