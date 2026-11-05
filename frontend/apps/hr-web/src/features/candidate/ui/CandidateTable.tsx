import { Table } from 'antd';
import { Link } from 'react-router-dom';
import type { Application, Candidate } from '@recruiter/domain';
import { StageBadge } from '@recruiter/ui-kit';

type Row = Candidate & { latest?: Application };

export function CandidateTable({ rows, loading }: { rows: Row[]; loading: boolean }) {
  return (
    <Table<Row>
      rowKey="id"
      loading={loading}
      dataSource={rows}
      pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: [20, 50, 100] }}
      locale={{ emptyText: '没有符合筛选条件的候选人。试试清除筛选。' }}
      columns={[
        { title: '候选人', render: (_, r) => <Link to={`/candidates/${r.id}`} style={{ fontWeight: 500 }}>{r.name}</Link> },
        { title: '当前职位', render: (_, r) => `${r.currentTitle}，${r.currentCompany}` },
        { title: '城市', dataIndex: 'city', width: 80 },
        { title: '经验', render: (_, r) => <span className="num">{r.years} 年</span>, width: 80, align: 'right' },
        { title: '进行中的应聘', render: (_, r) => (r.latest ? <span>{r.latest.positionName} <StageBadge stage={r.latest.stage} /></span> : <span className="muted">无</span>) },
        { title: '联系方式', dataIndex: 'phoneMasked', render: (v: string) => <span className="num">{v}</span> },
      ]}
    />
  );
}
