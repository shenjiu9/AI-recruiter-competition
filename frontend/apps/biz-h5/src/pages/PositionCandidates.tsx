import { useState } from 'react';
import { Button } from 'antd-mobile';
import { useQuery } from '@tanstack/react-query';
import { useApi, toAppError } from '@recruiter/api-client';

const STAGES: Record<string, string> = {
  reach: 'AI 触达',
  talking: '沟通中',
  ai_eval: 'AI 评估',
  interview: '面试',
  manager_eval: '用人部门评估',
  hired: '已录用',
  rejected: '已淘汰',
  withdrawn: '候选人放弃',
  transferred: '已转岗位',
  position_closed: '岗位关闭终止',
  declined: '未接受录用',
  no_show: '未入职',
  joined: '已入职',
};

function CandidateSummary({ id }: { id: string }) {
  const api = useApi();
  const q = useQuery({ queryKey: ['biz-candidate', id], queryFn: () => api.candidateRecord(id) });
  if (q.isError) return <p role="alert">{toAppError(q.error).message}</p>;
  if (!q.data) return <p>正在加载候选人…</p>;
  const c = q.data;
  return (
    <section aria-label="候选人资料">
      <h3>{c.profile.name}</h3>
      <p>
        {c.profile.company} · {c.profile.title} · {c.profile.city}
      </p>
      <p>手机：{c.profile.phone || '未填写'}</p>
      <p>邮箱：{c.profile.email || '未填写'}</p>
      <p>技能：{c.profile.skills || '待补全'}</p>
      <p style={{ whiteSpace: 'pre-wrap' }}>工作经历：{c.profile.experience || '待补全'}</p>
      <p>
        {c.profile.degree} · {c.profile.school}
      </p>
      <h4>
        投递记录 {c.applications.filter((a) => !a.restricted).length} / {c.applications.length}
      </h4>
      {c.applications.map((a) => (
        <p key={a.id}>
          {a.position_name} · {new Date(a.started_at).toLocaleDateString('zh-CN')} ·{' '}
          {STAGES[a.outcome ?? a.stage ?? ''] ?? '范围外记录'}
        </p>
      ))}
    </section>
  );
}

export function PositionCandidates({ id }: { id: string }) {
  const api = useApi();
  const [selected, setSelected] = useState('');
  const q = useQuery({
    queryKey: ['biz-position-candidates', id],
    queryFn: () => api.livePositionApplications(id),
    refetchInterval: 4000,
  });
  return (
    <div className="rm-card">
      <h2>岗位候选人</h2>
      {q.isError && <p role="alert">{toAppError(q.error).message}</p>}
      {q.data?.length === 0 && <p>暂未挂入候选人</p>}
      {q.data?.map((a) => (
        <article key={a.id} style={{ padding: '12px 0', borderBottom: '1px solid #ddd' }}>
          <strong>{a.candidate_name}</strong>
          <p>{STAGES[a.outcome ?? a.stage ?? '']}</p>
          <Button size="small" onClick={() => setSelected(a.candidate_id ?? '')}>
            查看候选人资料
          </Button>
          {selected === a.candidate_id && <CandidateSummary id={selected} />}
        </article>
      ))}
    </div>
  );
}
