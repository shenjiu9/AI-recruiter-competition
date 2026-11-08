import { Card, Statistic, Button, Tag, Empty, Skeleton, Alert, Avatar } from 'antd';
import {
  ArrowRightOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  TeamOutlined,
  SolutionOutlined,
  FileDoneOutlined,
  ScheduleOutlined,
  AuditOutlined,
} from '@ant-design/icons';
import { ActionButton } from './controls';
import { useCallback, useEffect, useRef, useState } from 'react';
import { DirectoryPersonPicker } from './DirectoryPersonPicker';
import {
  useApi,
  useReliableWrite,
  toAppError,
  type LiveHire,
  type HireCommand,
  type LiveCard,
  type CardCommand,
  type PositionInterviewRound,
} from '@recruiter/api-client';

export const HIRE_STATUS: Record<string, string> = {
  deciding: '待经理决定',
  pending: '审批中',
  approved: '已录用 · 待移交',
  handed_over: '已移交',
  accepted: '已接受',
  joined: '已入职',
  declined: '未接受',
  no_show: '未入职',
  rejected: '不录用',
  cancelled: '流程已变更',
};
const input = {
  display: 'block',
  width: '100%',
  boxSizing: 'border-box' as const,
  padding: 10,
  fontSize: 16,
  marginBlock: 8,
};
const section = {
  background: 'var(--rc-surface)',
  padding: 16,
  border: '1px solid var(--rc-line)',
  borderRadius: 16,
  marginBlock: 16,
};

export function useLiveData<T>(key: string, load: () => Promise<T>) {
  const loader = useRef(load);
  loader.current = load;
  const serial = useRef(0);
  const invalidate = useCallback(() => {
    serial.current++;
  }, []);
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    const n = ++serial.current;
    try {
      const value = await loader.current();
      if (n === serial.current) {
        setData(value);
        setError('');
      }
      return value;
    } catch (e) {
      if (n === serial.current) setError(toAppError(e).message);
      return undefined;
    }
  }, []);
  const update = (v: T) => {
    serial.current++;
    setData(v);
    setError('');
  };
  useEffect(() => {
    setData(undefined);
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => {
      clearInterval(timer);
      invalidate();
    };
  }, [key, refresh, invalidate]);
  return { data, error, refresh, update };
}

export function HiringList({ filters = {} }: { filters?: Record<string, string> }) {
  const api = useApi();
  const [page, setPage] = useState(1);
  const q = useLiveData(JSON.stringify([filters, page]), () => api.liveHires(page, filters));
  return (
    <main className="rc-live-page" style={{ maxWidth: 1100, margin: 'auto', padding: 16 }}>
      <h1>录用决定与移交</h1>
      <p>经理查看完整面评后决定，审批通过后由 HR 移交现有流程并回填结果。</p>
      {q.error && <p role="alert">{q.error}</p>}
      {q.data?.items.map((h) => (
        <article key={h.id} style={section}>
          <h2>
            <a href={`/hiring/${h.id}`}>
              {h.candidate_name} · {h.position_name}
            </a>
          </h2>
          <p>
            {HIRE_STATUS[h.status]} · 岗位可招 {h.remaining} 人
          </p>
          <p>
            面评均分：
            {Object.entries(h.averages)
              .map(([k, v]) => `${k} ${v}`)
              .join('，')}
          </p>
        </article>
      ))}
      {q.data?.total === 0 && <p>暂无可见录用记录。</p>}
      <ActionButton disabled={page === 1} onClick={() => setPage(page - 1)}>
        上一页
      </ActionButton>{' '}
      第 {page} 页{' '}
      <ActionButton disabled={page * 20 >= (q.data?.total ?? 0)} onClick={() => setPage(page + 1)}>
        下一页
      </ActionButton>
    </main>
  );
}

export function HiringDetail({ id }: { id: string }) {
  const api = useApi();
  const q = useLiveData(id, () => api.liveHire(id));
  return (
    <main className="rc-live-page" style={{ maxWidth: 900, margin: 'auto', padding: 16 }}>
      <a href="/hiring">返回录用列表</a>
      {q.error ? (
        <p role="alert">{q.error}</p>
      ) : q.data ? (
        <HireForm key={id} h={q.data} update={q.update} refresh={q.refresh} />
      ) : (
        <p>正在加载…</p>
      )}
    </main>
  );
}

function HireForm({
  h,
  update,
  refresh,
}: {
  h: LiveHire;
  update: (h: LiveHire) => void;
  refresh: () => Promise<unknown>;
}) {
  const api = useApi();
  const [downloadError, setDownloadError] = useState('');
  const [verifiedAt, setVerifiedAt] = useState('');
  const verified = verifiedAt === h.review_stamp;
  const setVerified = (value: boolean) => setVerifiedAt(value ? h.review_stamp : '');
  const [reason, setReason] = useState('');
  const [salary, setSalary] = useState(h.facts?.salary_k ?? 10);
  const [months, setMonths] = useState(h.facts?.salary_months ?? 13);
  const [start, setStart] = useState(h.facts?.expected_start ?? '');
  const [evidence, setEvidence] = useState('');
  const [owner, setOwner] = useState(h.facts?.offer_owner ?? '');
  const [extra, setExtra] = useState<PositionInterviewRound>({
    name: '补充面试',
    format: 'phone',
    duration: 30,
    interviewers: [],
    rule: 'unanimous',
    criteria: '专业能力\n沟通能力',
  });
  const [result, setResult] = useState<HireCommand['result']>('accepted');
  const op = useReliableWrite<HireCommand, LiveHire>(
    (b, o) => api.hireCommand(h.id, b, o),
    (v) => {
      update(v);
      setVerified(false);
    },
  );
  const run = (action: HireCommand['action'], body: Partial<HireCommand> = {}) =>
    void op.submit({
      action,
      expected_version: h.version,
      review_stamp: h.review_stamp,
      verified,
      reason,
      ...body,
    });
  return (
    <article aria-label="录用详情">
      <h1>{h.candidate_name} · 录用评估</h1>
      <p>
        {h.position_name} · {HIRE_STATUS[h.status]} · 可招 {h.remaining} 人
      </p>
      <section style={section}>
        <h2>面评汇总</h2>
        <p>AI 录用建议尚未接入，以下为本人提交的面评。</p>
        <p>
          各维度均分：
          {Object.entries(h.averages)
            .map(([k, v]) => `${k} ${v}`)
            .join('，')}
        </p>
        {h.feedback.map((iv) => (
          <details key={iv.id} open>
            <summary>
              {iv.round_name} · {iv.result === 'pass' ? '通过' : '待人工决策'}
            </summary>
            {Object.values(iv.feedback).map((f) => (
              <div key={f.author}>
                <p>
                  {f.author} ·{' '}
                  {
                    (
                      { yes: '推荐', strong_yes: '强烈推荐', hold: '待定', no: '不推荐' } as Record<
                        string,
                        string
                      >
                    )[f.recommendation]
                  }
                </p>
                <p>优势：{f.strengths}</p>
                <p>顾虑：{f.concerns || '无'}</p>
                <p>
                  {Object.entries(f.scores)
                    .map(([k, v]) => `${k} ${v} 分`)
                    .join('，')}
                </p>
                {Object.entries(f.answers).map(([k, v]) => (
                  <p key={k}>
                    {k}：{v}
                  </p>
                ))}
              </div>
            ))}
          </details>
        ))}
      </section>
      <section style={section}>
        <h2>录用前核实</h2>
        {h.facts ? (
          <>
            <p>薪资带宽：{h.facts.salary_over ? '超带宽，须 HRD 加签' : '在带宽内'}</p>
            {h.facts.salary_k !== undefined && (
              <p>
                候选人期望：{h.facts.salary_k} K/月 × {h.facts.salary_months} 月
              </p>
            )}
            <p>
              预计到岗：{h.facts.expected_start} · 移交负责人：{h.facts.offer_owner}
            </p>
          </>
        ) : (
          <p>等待 HR 核实候选人期望薪资、到岗时间和移交负责人。</p>
        )}
        <fieldset disabled={op.locked} style={{ border: 0, padding: 0 }}>
          {h.can_prepare && (
            <>
              <label>
                候选人期望月薪（K）
                <input
                  aria-label="候选人期望月薪"
                  style={input}
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={salary}
                  onChange={(e) => setSalary(Number(e.target.value))}
                />
              </label>
              <label>
                年度薪资月数
                <input
                  aria-label="年度薪资月数"
                  style={input}
                  type="number"
                  value={months}
                  onChange={(e) => setMonths(Number(e.target.value))}
                />
              </label>
            </>
          )}
          {(h.can_prepare || h.can_result) && (
            <label>
              预计入职日期
              <input
                style={input}
                aria-label="预计入职日期"
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
          )}
          {(h.can_prepare || h.can_handover) && (
            <div>
              <label htmlFor="hire-owner">移交负责人</label>
              <DirectoryPersonPicker
                id="hire-owner"
                label="移交负责人"
                dept={h.department}
                value={owner ? [owner] : []}
                onChange={(ids) => setOwner(ids[0] ?? '')}
                disabled={op.locked}
              />
            </div>
          )}
          {(h.can_prepare || h.can_handover) && (
            <label>
              核实证据 / 移交凭证
              <textarea
                aria-label="核实证据或移交凭证"
                style={input}
                value={evidence}
                onChange={(e) => setEvidence(e.target.value)}
                maxLength={2000}
              />
            </label>
          )}
          <label style={{ display: 'block', marginBlock: 12 }}>
            <input
              type="checkbox"
              checked={verified}
              onChange={(e) => setVerified(e.target.checked)}
            />
            我已查看面评汇总并核实本次操作内容
          </label>
          {h.can_prepare && (
            <ActionButton
              disabled={!verified || !start || !owner || !evidence}
              onClick={() =>
                run('prepare', {
                  salary_k: salary,
                  salary_months: months,
                  expected_start: start,
                  offer_owner: owner,
                  evidence,
                })
              }
            >
              保存核实信息
            </ActionButton>
          )}
          <label>
            决定 / 驳回 / 结果原因
            <textarea
              aria-label="录用操作原因"
              style={input}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={2000}
            />
          </label>
          {h.can_decide && (
            <>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <ActionButton
                  disabled={!verified || !h.facts}
                  onClick={() => run('decide', { decision: 'hire' })}
                >
                  决定录用并发起审批
                </ActionButton>
                <ActionButton
                  disabled={!verified || !reason}
                  onClick={() => run('decide', { decision: 'reject' })}
                >
                  决定不录用
                </ActionButton>
              </div>
              <details style={{ marginTop: 12 }}>
                <summary>追加一轮面试</summary>
                <label>
                  面试官账号（逗号分隔）
                  <input
                    aria-label="追加面试官"
                    style={input}
                    value={extra.interviewers.join(',')}
                    onChange={(e) =>
                      setExtra({
                        ...extra,
                        interviewers: e.target.value
                          .split(',')
                          .map((v) => v.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </label>
                <label>
                  本轮评价维度
                  <textarea
                    style={input}
                    value={extra.criteria}
                    onChange={(e) => setExtra({ ...extra, criteria: e.target.value })}
                  />
                </label>
                <ActionButton
                  disabled={!verified || !reason || !extra.interviewers.length}
                  onClick={() => run('decide', { decision: 'extra_round', extra_round: extra })}
                >
                  确认追加面试
                </ActionButton>
              </details>
            </>
          )}
          {h.can_approve && (
            <div style={{ display: 'flex', gap: 12 }}>
              <ActionButton disabled={!verified} onClick={() => run('approve')}>
                通过录用审批
              </ActionButton>
              <ActionButton disabled={!verified || !reason} onClick={() => run('reject')}>
                驳回录用审批
              </ActionButton>
            </div>
          )}
          {h.can_withdraw && (
            <ActionButton disabled={!reason} onClick={() => run('withdraw')}>
              撤回本次录用审批
            </ActionButton>
          )}
          {h.can_handover && (
            <>
              <p>请先把移交单交给负责 HR，再登记实际交接凭证。系统尚未接入飞书发送。</p>
              <ActionButton
                disabled={!verified || !evidence}
                onClick={() =>
                  run('handover', { evidence, offer_owner: owner || h.facts?.offer_owner })
                }
              >
                登记已实际移交
              </ActionButton>
            </>
          )}
          {h.can_result && (
            <>
              <label>
                回填结果
                <select
                  aria-label="回填结果"
                  style={input}
                  value={result}
                  onChange={(e) => setResult(e.target.value as HireCommand['result'])}
                >
                  {Object.entries({
                    accepted: '已接受',
                    declined: '未接受',
                    joined: '已入职',
                    no_show: '未入职',
                  }).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <ActionButton
                disabled={!verified}
                onClick={() =>
                  run('result', { result, ...(start ? { expected_start: start } : {}) })
                }
              >
                保存录用结果
              </ActionButton>
            </>
          )}
        </fieldset>
      </section>
      {op.error && <p role="alert">{op.error}</p>}
      {op.retry && (
        <ActionButton onClick={op.retryAction} disabled={op.busy}>
          重试本次操作
        </ActionButton>
      )}
      {op.conflict && (
        <ActionButton
          onClick={async () => {
            await refresh();
            op.refreshed();
            setVerified(false);
          }}
        >
          刷新录用记录
        </ActionButton>
      )}
      <section style={section}>
        <h2>审批记录</h2>
        {h.chain.map((n, i) => (
          <p key={i}>
            {n.name} ·{' '}
            {n.role === 'salary' ? 'HRD 加签' : n.role === 'director' ? '部门负责人' : 'HRBP'} ·{' '}
            {
              (
                { pending: '待审批', approved: '已通过', rejected: '已驳回' } as Record<
                  string,
                  string
                >
              )[n.status]
            }{' '}
            {n.reason}
          </p>
        ))}
      </section>
      {h.handoff && (
        <section style={section}>
          <h2>录用移交单</h2>
          <ActionButton
            onClick={async () => {
              try {
                const blob = await api.downloadHireHandoff(h.id);
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = '录用移交单.xlsx';
                link.click();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
                setDownloadError('');
              } catch (e) {
                setDownloadError(toAppError(e).message);
              }
            }}
          >
            下载移交单（Excel）
          </ActionButton>
          {downloadError && <p role="alert">{downloadError}</p>}
          <p>{h.handoff.delivery === 'manual_confirmed' ? '已人工确认移交' : '待人工移交'}</p>
          <p>
            候选人：{h.handoff.candidate.name} · {h.handoff.candidate.phone} ·{' '}
            {h.handoff.candidate.email}
          </p>
          <p>
            岗位：{h.position_name} · {h.handoff.position.level} · {h.handoff.position.city}
          </p>
          <p>汇报对象：{h.handoff.position.reportTo}</p>
          <p>
            期望薪资：{h.handoff.facts.salary_k} K/月 × {h.handoff.facts.salary_months}
          </p>
          <p>预计到岗：{h.handoff.facts.expected_start}</p>
          <p>交接负责人：{h.handoff.facts.offer_owner}</p>
          <p>面评与审批记录见本页上方。</p>
          {h.handoff.evidence && <p>交接凭证：{h.handoff.evidence}</p>}
        </section>
      )}
      {h.result && (
        <p>
          回填：{HIRE_STATUS[h.result.value]} {h.result.reason} {h.result.expected_start}
        </p>
      )}
      {h.reminders.map((r) => (
        <p key={r.key}>
          站内提醒：{r.kind === 'decision' ? '录用决定或审批超时' : '移交后结果待回填'} ·{' '}
          {new Date(r.at).toLocaleString()}
        </p>
      ))}
    </article>
  );
}

export function LiveWorkbench({ business = false }: { business?: boolean }) {
  const api = useApi();
  const q = useLiveData('workbench', () => api.liveWorkbench());
  const metrics = [
    { key: 'open_positions', label: '招聘中岗位', icon: <SolutionOutlined /> },
    { key: 'remaining', label: '可招人数', icon: <TeamOutlined /> },
    { key: 'cards', label: '待处理卡片', icon: <AuditOutlined /> },
    { key: 'my_approvals', label: '待我审批', icon: <FileDoneOutlined /> },
    { key: 'pending_handoffs', label: '待移交', icon: <ScheduleOutlined /> },
    { key: 'pending_results', label: '待回填结果', icon: <CheckCircleOutlined /> },
  ];
  const stages = [
    { key: 'talking', label: '沟通' },
    { key: 'ai_eval', label: '评估' },
    { key: 'interview', label: '面试' },
    { key: 'manager_eval', label: '业务评估' },
  ];
  return (
    <main className="rc-workbench">
      <header className="rc-overview-header">
        <div>
          <span className="rc-eyebrow">YOUR RECRUITING DAY</span>
          <h1>招聘工作台</h1>
          <p>从每一次沟通开始，让合适的人与机会相遇。</p>
        </div>
        <span className="rc-date">
          <ScheduleOutlined />{' '}
          {new Date().toLocaleDateString('zh-CN', {
            month: 'long',
            day: 'numeric',
            weekday: 'long',
          })}
        </span>
      </header>
      {q.error && (
        <Alert
          type="error"
          showIcon
          message={q.error}
          action={<Button onClick={() => void q.refresh()}>重新加载</Button>}
        />
      )}
      <div className="rc-metrics">
        {metrics.map((m) => (
          <Card className="rc-metric" key={m.key}>
            <div className="rc-metric-top">
              <span>{m.label}</span>
              {m.icon}
            </div>
            {q.data ? (
              <Statistic value={q.data.counts[m.key] ?? 0} />
            ) : (
              <Skeleton.Input active size="small" />
            )}
          </Card>
        ))}
      </div>
      <div className="rc-dashboard-grid">
        <div className="rc-dashboard-main">
          <Card
            title="待我审批的招聘需求"
            extra={<a href={business ? '/' : '/requisitions'}>查看招聘需求</a>}
          >
            {!q.data ? (
              <Skeleton active />
            ) : q.data.requisition_approvals?.length ? (
              q.data.requisition_approvals.map((req) => (
                <p key={req.id}>
                  <a href={business ? `/?review=${req.id}` : `/requisitions/${req.id}`}>
                    {req.title} · 去审批
                  </a>
                  <span className="muted"> · {req.dept}</span>
                </p>
              ))
            ) : (
              <p className="muted">目前没有轮到你处理的招聘需求。</p>
            )}
          </Card>
          <Card>
            <div className="rc-section-heading">
              <div>
                <h2>待处理决策卡</h2>
                <p>把注意力留给需要你判断的事情</p>
              </div>
              <Tag bordered={false} color="cyan">
                {q.data?.cards.length ?? '—'} 项待办
              </Tag>
            </div>
            {!q.data ? (
              <Skeleton active />
            ) : q.data.cards.length ? (
              q.data.cards.map((c) => <DecisionItem key={c.id} c={c} refresh={q.refresh} />)
            ) : (
              <div className="rc-empty">
                <div className="rc-empty-icon">
                  <CheckCircleOutlined />
                </div>
                <h3>当前决策卡已处理完</h3>
                <p>暂无待处理卡片。</p>
                <span className="muted">新的决策与提醒会出现在这里</span>
              </div>
            )}
          </Card>
          <Card>
            <div className="rc-section-heading">
              <div>
                <h2>岗位与招聘进展</h2>
                <p>从沟通到面试，进度一目了然</p>
              </div>
              <a href="/positions">
                全部岗位 <ArrowRightOutlined />
              </a>
            </div>
            {!q.data ? (
              <Skeleton active />
            ) : !q.data.positions.length ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无可见岗位，审批通过后会生成岗位。"
              />
            ) : (
              q.data.positions.map((p) => (
                <article className="rc-position-row" key={p.id}>
                  <div className="rc-position-row-title">
                    <a href={`/positions/${p.id}`}>{p.name}</a>
                    <Tag bordered={false} color="cyan">
                      可招 {p.remaining} 人
                    </Tag>
                  </div>
                  <p className="rc-position-meta">
                    计划 {p.planned} 人 <span> · </span> 已录用 {p.hired} 人
                  </p>
                  <div className="rc-stage-track">
                    {stages.map((stage) => (
                      <div
                        className="rc-stage-cell"
                        data-active={!!p.stages[stage.key]}
                        key={stage.key}
                      >
                        <span>{stage.label}</span>
                        <strong>{p.stages[stage.key] ?? 0}</strong>
                      </div>
                    ))}
                  </div>
                </article>
              ))
            )}
          </Card>
          <Card>
            <div className="rc-section-heading">
              <div>
                <h2>录用待办</h2>
                <p>及时完成审批、移交与结果回填</p>
              </div>
              <a href="/hiring">
                查看全部 <ArrowRightOutlined />
              </a>
            </div>
            {q.data?.hires.length ? (
              q.data.hires.map((h) => (
                <div className="rc-hire-row" key={h.id}>
                  <Avatar style={{ background: 'var(--rc-brand-soft)', color: 'var(--rc-brand)' }}>
                    {h.candidate_name.slice(0, 1)}
                  </Avatar>
                  <a href={`/hiring/${h.id}`}>
                    {h.candidate_name} · {h.position_name}
                  </a>
                  <Tag style={{ marginLeft: 'auto' }}>{HIRE_STATUS[h.status]}</Tag>
                </div>
              ))
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无录用待办" />
            )}
          </Card>
        </div>
        <aside className="rc-dashboard-rail">
          <Card className="rc-assistant-card">
            <div className="rc-assistant-orbit" aria-hidden="true" />
            <span className="rc-eyebrow">YOUR AI COPILOT</span>
            <ThunderboltOutlined style={{ fontSize: 28, color: 'var(--rc-ai)' }} />
            <h2>
              多一点洞察，
              <br />
              少一点重复。
            </h2>
            <p>
              让 AI 协助整理信息与证据，
              <br />
              重要的决定，始终由你把握。
            </p>
            <Button type="primary" href="/ai-jobs" icon={<ArrowRightOutlined />}>
              查看 AI 任务与复核
            </Button>
          </Card>
          <Card>
            <div className="rc-section-heading">
              <h2>快捷入口</h2>
            </div>
            <div className="rc-quicklinks">
              <a className="rc-quicklink" href="/positions">
                <SolutionOutlined />
                <span>岗位与画像</span>
                <ArrowRightOutlined />
              </a>
              <a className="rc-quicklink" href="/interviews">
                <ScheduleOutlined />
                <span>面试与面评</span>
                <ArrowRightOutlined />
              </a>
              <a className="rc-quicklink" href="/hiring">
                <FileDoneOutlined />
                <span>录用决定、移交与结果回填</span>
                <ArrowRightOutlined />
              </a>
            </div>
          </Card>
          <p style={{ fontSize: 12, color: 'var(--rc-ink-3)', padding: '0 6px', margin: 0 }}>
            仅展示当前账号权限范围内的数据。
          </p>
        </aside>
      </div>
    </main>
  );
}

function DecisionItem({ c, refresh }: { c: LiveCard; refresh: () => Promise<unknown> }) {
  const api = useApi();
  const [reason, setReason] = useState('');
  const op = useReliableWrite<CardCommand, LiveCard>(
    (b, o) => api.resolveLiveCard(c.id, b, o),
    () => {
      void refresh();
    },
  );
  return (
    <article style={section}>
      <h3>{c.title}</h3>
      <p>来源：业务规则 · {c.overdue ? '已超时，等待人工处理' : '等待人工处理'}</p>
      <a href={c.href}>打开详情核实</a>
      <fieldset disabled={op.locked} style={{ border: 0, padding: 0 }}>
        <label>
          处理原因
          <input
            style={input}
            aria-label={`卡片原因 ${c.id}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        {c.options.map((o) => (
          <ActionButton
            style={{ marginRight: 10 }}
            disabled={!reason}
            key={o}
            onClick={() =>
              void op.submit({
                expected_version: c.version,
                option: o as CardCommand['option'],
                reason,
              })
            }
          >
            {
              (
                {
                  reject: '确认淘汰',
                  terminate: '终止本次应聘',
                  keep: '保留当前流程',
                  dismiss: '已阅，关闭此提醒',
                } as Record<string, string>
              )[o]
            }
          </ActionButton>
        ))}
      </fieldset>
      {op.error && <p role="alert">{op.error}</p>}
      {op.retry && <ActionButton onClick={op.retryAction}>重试本次操作</ActionButton>}
    </article>
  );
}
