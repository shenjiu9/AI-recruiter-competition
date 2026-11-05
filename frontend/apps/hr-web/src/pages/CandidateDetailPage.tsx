import { App, Breadcrumb, Skeleton, Table, Tabs, Timeline } from 'antd';
import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { formatDate, formatDateTime, type EvidenceRef } from '@recruiter/domain';
import { usePermission } from '@recruiter/permissions';
import { track, usePageView } from '@recruiter/telemetry';
import { ConversationPanel, EmptyState, ResumeViewer, StageBadge } from '@recruiter/ui-kit';
import { ApplicationStrip, CandidateHeader, EvaluationPanel, useCandidateDetail, useConversationActions } from '../features/candidate';

/** CD-02 候选人详情：评估与简历并排，证据一点就对上 */
export function CandidateDetailPage() {
  usePageView('CD-02');
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const [appId, setAppId] = useState<string | undefined>();
  const d = useCandidateDetail(id, appId);
  const conv = useConversationActions(id);
  const canTake = usePermission('conversation.take_over');
  const [refs, setRefs] = useState<string[]>([]);
  const { message } = App.useApp();
  const tab = params.get('tab') ?? 'eval';

  const onEvidence = (e: EvidenceRef) => {
    if (e.kind === 'resume') setRefs((cur) => (cur.length === 1 && cur[0] === e.ref ? [] : [e.ref]));
    else if (e.kind === 'message') {
      setParams({ tab: 'conversation' });
    }
  };

  if (d.candidate.isLoading) return <Skeleton active />;
  if (!d.candidate.data) return <EmptyState title="找不到这位候选人" why="可能已被合并、删除，或者不在你的数据范围内。" action={<Link to="/candidates">回到人才库</Link>} />;
  const c = d.candidate.data;

  return (
    <div>
      <Breadcrumb style={{ marginBottom: 12 }} items={[{ title: <Link to="/candidates">候选人</Link> }, { title: c.name }]} />
      <CandidateHeader c={c} />
      {d.applications.data && (
        <ApplicationStrip
          apps={d.applications.data}
          currentId={d.appId}
          onSelect={(x) => {
            setAppId(x);
            setRefs([]);
            track('cd_app_switch');
          }}
        />
      )}
      <Tabs
        activeKey={tab}
        onChange={(k) => setParams({ tab: k })}
        items={[
          {
            key: 'eval',
            label: '评估与简历',
            children: (
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 5fr) minmax(0, 7fr)', gap: 24, alignItems: 'start' }}>
                <section className="panel" style={{ padding: 16 }} aria-label="AI 评估表">
                  <EvaluationPanel ev={d.evaluation.data} activeRefs={refs} onEvidence={onEvidence} onAsk={() => message.success('已加入补问，AI 会在下一条消息里问候选人')} />
                </section>
                <section className="panel" style={{ padding: 16, position: 'sticky', top: 80, maxHeight: 'calc(100vh - 120px)', overflow: 'auto' }} aria-label="简历原文">
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <strong style={{ fontWeight: 500 }}>简历原文</strong>
                    <span className="muted" style={{ fontSize: 12 }}>{d.resume.data?.fileName}</span>
                  </div>
                  {d.resume.data ? <ResumeViewer resume={d.resume.data} activeRefs={refs} /> : <Skeleton active />}
                </section>
              </div>
            ),
          },
          {
            key: 'conversation',
            label: '会话',
            children: d.conversation.data ? (
              <div className="panel" style={{ padding: 16, maxWidth: 820 }}>
                <ConversationPanel
                  conversation={d.conversation.data}
                  candidateName={c.name}
                  canTakeOver={canTake}
                  onTakeOver={async () => {
                    await conv.takeOver.mutateAsync();
                    track('conv_takeover', { trigger: d.conversation.data?.mode });
                  }}
                  onHandBack={async () => {
                    await conv.handBack.mutateAsync();
                    track('conv_handback');
                  }}
                  onSend={async (t) => {
                    await conv.send.mutateAsync(t);
                  }}
                />
              </div>
            ) : (
              <Skeleton active />
            ),
          },
          {
            key: 'applications',
            label: '投递记录',
            children: (
              <Table
                rowKey="id"
                pagination={false}
                dataSource={d.applications.data ?? []}
                columns={[
                  { title: '岗位', render: (_, a) => <Link to={`/positions/${a.positionId}`}>{a.positionName}</Link> },
                  { title: '开始时间', render: (_, a) => <span className="num">{formatDate(a.startedAt)}</span> },
                  { title: '来源', dataIndex: 'source' },
                  { title: '阶段或结论', render: (_, a) => <StageBadge stage={a.stage} ended={a.ended?.result} /> },
                  { title: '原因', render: (_, a) => a.ended?.reason ?? a.subStatus },
                ]}
              />
            ),
          },
          {
            key: 'logs',
            label: '操作记录',
            children: (
              <Timeline
                style={{ maxWidth: 820, paddingTop: 8 }}
                items={(d.logs.data ?? []).map((l) => ({
                  color: l.isAi ? 'var(--rc-ai)' : 'var(--rc-brand)',
                  children: (
                    <div>
                      <span className="num muted" style={{ marginRight: 12, fontSize: 12 }}>{formatDateTime(l.at)}</span>
                      {l.isAi && <span className="rc-tag rc-ai" style={{ marginRight: 6 }}>AI</span>}
                      <span>{l.actor}</span>
                      <div>{l.text}</div>
                    </div>
                  ),
                }))}
              />
            ),
          },
        ]}
      />
    </div>
  );
}
