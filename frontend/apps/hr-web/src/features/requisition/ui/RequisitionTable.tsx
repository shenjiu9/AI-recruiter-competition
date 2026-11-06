import { Table } from 'antd';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '@recruiter/api-client';
import { POSITION_STATUS_LABEL } from '@recruiter/domain';
import { REQ_STATUS_LABEL, REQ_TYPE_LABEL, formatDate, type Requisition } from '@recruiter/domain';

const REQ_TONE = {
  draft: 'muted',
  in_approval: 'active',
  approved: 'ok',
  rejected: 'bad',
  withdrawn: 'muted',
} as const;

const MODE = { self: '本人发起', proxy: '代发起', ai_draft: 'AI 起草' } as const;

function GeneratedPosition({ reqId }: { reqId: string }) {
  const api = useApi();
  const query = useQuery({
    queryKey: ['position-generation', reqId],
    queryFn: () => api.positionGeneration(reqId),
    refetchInterval: 5000,
  });
  if (query.isError) return <Link to={`/requisitions/${reqId}`}>查看生成状态</Link>;
  const pos = query.data?.position;
  return pos ? (
    <Link to={`/positions/${pos.id}`}>
      {pos.name} · {POSITION_STATUS_LABEL[pos.status]}
    </Link>
  ) : (
    <Link to={`/requisitions/${reqId}`}>
      {query.data?.status === 'decision' ? '待选择合并 / 新建' : '生成处理中'}
    </Link>
  );
}

function waiting(r: Requisition) {
  if (r.status === 'in_approval')
    return (
      <span style={{ color: (r.waitingDays ?? 0) > 2 ? 'var(--rc-warn)' : undefined }}>
        等{r.waitingFor}审批，已 {r.waitingDays} 天
      </span>
    );
  if (r.status === 'draft') return `等${r.waitingFor}提交`;
  if (r.status === 'rejected') return `等${r.waitingFor}修改`;
  return null;
}

export function RequisitionTable({
  rows,
  loading,
  page,
  total,
  onPageChange,
}: {
  rows: Requisition[];
  loading: boolean;
  page: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <Table<Requisition>
      rowKey="id"
      loading={loading}
      dataSource={rows}
      pagination={{
        current: page,
        total,
        pageSize: 20,
        onChange: onPageChange,
        showSizeChanger: false,
      }}
      columns={[
        {
          title: '需求',
          render: (_, r) => (
            <div>
              <Link to={`/requisitions/${r.id}`}>{r.title}</Link>
              <div className="muted num" style={{ fontSize: 12 }}>
                {r.no}
              </div>
            </div>
          ),
        },
        { title: '需求部门', dataIndex: 'dept' },
        { title: '类型与人数', render: (_, r) => `${REQ_TYPE_LABEL[r.type]}，${r.headcount} 人` },
        {
          title: '发起',
          render: (_, r) => (
            <span>
              {r.initiator}
              <span className="muted" style={{ marginLeft: 6, fontSize: 12 }}>
                {r.mode === 'proxy' ? `${r.proxyBy}代发起` : MODE[r.mode]}
              </span>
            </span>
          ),
        },
        {
          title: '状态',
          render: (_, r) => (
            <span className="rc-status" data-tone={REQ_TONE[r.status]}>
              {REQ_STATUS_LABEL[r.status]}
            </span>
          ),
        },
        { title: '当前在等', render: (_, r) => waiting(r) },
        {
          title: '生成的岗位',
          render: (_, r) =>
            import.meta.env.VITE_USE_MOCK === 'false' && r.status === 'approved' ? (
              <GeneratedPosition reqId={r.id} />
            ) : r.positionId ? (
              <Link to={`/positions/${r.positionId}`}>{r.title}</Link>
            ) : null,
        },
        {
          title: '提交时间',
          align: 'right',
          render: (_, r) =>
            r.submittedAt ? (
              <span className="num">{formatDate(r.submittedAt)}</span>
            ) : (
              <span className="muted">未提交</span>
            ),
          defaultSortOrder: 'descend',
          sorter: (a, b) => (a.submittedAt ?? '').localeCompare(b.submittedAt ?? ''),
        },
      ]}
    />
  );
}
