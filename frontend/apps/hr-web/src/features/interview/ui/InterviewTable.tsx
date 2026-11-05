import { Table } from 'antd';
import { Link } from 'react-router-dom';
import { INTERVIEW_STATUS_LABEL, formatSlot, type Interview } from '@recruiter/domain';

export function InterviewTable({ rows, loading }: { rows: Interview[]; loading: boolean }) {
  return (
    <Table<Interview>
      rowKey="id"
      loading={loading}
      dataSource={rows}
      pagination={false}
      columns={[
        { title: '时间', width: 230, render: (_, r) => (r.start && r.end ? <span className="num">{formatSlot(r.start, r.end)}</span> : <span className="muted">{INTERVIEW_STATUS_LABEL[r.status]}</span>) },
        { title: '候选人', render: (_, r) => <Link to={`/candidates/${r.candidateId}`} style={{ fontWeight: 500 }}>{r.candidateName}</Link> },
        { title: '岗位', dataIndex: 'positionName' },
        { title: '轮次', render: (_, r) => `第 ${r.round} 轮，${r.roundName}` },
        { title: '形式', dataIndex: 'form', width: 80 },
        { title: '面试官', render: (_, r) => r.interviewers.join('、') },
        {
          title: '状态',
          render: (_, r) => (
            <div>
              {INTERVIEW_STATUS_LABEL[r.status]}
              {r.conflict && <div style={{ fontSize: 12, color: 'var(--rc-warn)' }}>{r.conflict}</div>}
            </div>
          ),
        },
        {
          title: '面评',
          align: 'right',
          render: (_, r) => <span className="num" style={{ color: r.status === 'to_feedback' && r.feedbackDone < r.feedbackTotal ? 'var(--rc-warn)' : undefined }}>已交 {r.feedbackDone} / {r.feedbackTotal}</span>,
        },
      ]}
    />
  );
}
