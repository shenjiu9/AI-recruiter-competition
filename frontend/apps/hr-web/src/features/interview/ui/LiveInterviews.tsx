import { useState } from 'react';
import { Alert, Button, Select, Space, Table } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useApi, toAppError, type LiveInterview } from '@recruiter/api-client';
import { InterviewDetails, INTERVIEW_STATUS } from '@recruiter/ui-kit/interview-details';

export function LiveInterviewList({
  positionId,
  candidateId,
}: {
  positionId?: string;
  candidateId?: string;
}) {
  const api = useApi();
  const [params] = useSearchParams();
  const [page, setPage] = useState(1);
  const [state, setState] = useState('');
  const [mine, setMine] = useState(false);
  const position = positionId ?? params.get('position_id') ?? '';
  const app = params.get('application_id') ?? '';
  const candidate = candidateId ?? params.get('candidate_id') ?? '';
  const query = useQuery({
    queryKey: ['live-interviews', position, candidate, app, state, page, mine],
    queryFn: () =>
      api.liveInterviews(page, {
        position_id: position,
        candidate_id: candidate,
        application_id: app,
        state,
        mine: String(mine),
      }),
    refetchInterval: 5000,
  });
  return (
    <section aria-label="面试日程">
      <h2>{positionId ? '岗位面试日程' : candidateId ? '候选人面试记录' : '面试日程'}</h2>
      <p>跨岗位检查面试官与候选人时间冲突。外部日历和会议当前由 HR 核实。</p>
      <Space wrap>
        <Select
          aria-label="面试状态筛选"
          value={state}
          style={{ width: 160 }}
          options={[
            { value: '', label: '全部状态' },
            ...Object.entries(INTERVIEW_STATUS).map(([value, label]) => ({ value, label })),
          ]}
          onChange={(v) => {
            setState(v);
            setPage(1);
          }}
        />
        <Button
          onClick={() => {
            setMine(!mine);
            setPage(1);
          }}
        >
          {mine ? '查看范围内全部' : '只看我参与的'}
        </Button>
      </Space>
      {query.isError && (
        <Alert role="alert" type="error" message={toAppError(query.error).message} />
      )}
      <Table<LiveInterview>
        rowKey="id"
        dataSource={query.data?.items ?? []}
        loading={query.isLoading}
        scroll={{ x: 760 }}
        pagination={{
          current: page,
          pageSize: 20,
          total: query.data?.total ?? 0,
          onChange: setPage,
          showSizeChanger: false,
        }}
        columns={[
          {
            title: '时间',
            render: (_, r) => (r.start ? new Date(r.start).toLocaleString() : '待约'),
          },
          {
            title: '候选人',
            render: (_, r) => <Link to={`/candidates/${r.candidate_id}`}>{r.candidate_name}</Link>,
          },
          {
            title: '岗位',
            render: (_, r) => <Link to={`/positions/${r.position_id}`}>{r.position_name}</Link>,
          },
          { title: '轮次', render: (_, r) => `${r.round_no} · ${r.round_name}` },
          { title: '状态', render: (_, r) => INTERVIEW_STATUS[r.status] },
          {
            title: '面评',
            render: (_, r) => `${r.feedback_count ?? 0} / ${r.interviewers?.length ?? 0}`,
          },
          { title: '操作', render: (_, r) => <Link to={`/interviews/${r.id}`}>查看面试详情</Link> },
        ]}
      />
    </section>
  );
}

export function LiveInterviewPage() {
  const { id = '' } = useParams();
  const api = useApi();
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ['live-interview', id],
    queryFn: () => api.liveInterview(id),
    refetchInterval: 5000,
  });
  return (
    <div>
      <Link to="/interviews">返回面试日程</Link>
      {query.isError ? (
        <Alert role="alert" type="error" message={toAppError(query.error).message} />
      ) : query.data ? (
        <InterviewDetails
          key={id}
          interview={query.data}
          refresh={query.refetch}
          onUpdated={(iv) => {
            cache.setQueryData(['live-interview', id], iv);
            void cache.invalidateQueries({ queryKey: ['live-interviews'] });
          }}
        />
      ) : (
        <p>正在加载…</p>
      )}
    </div>
  );
}
