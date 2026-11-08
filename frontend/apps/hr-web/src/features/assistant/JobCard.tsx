import { CheckCircleFilled, LoadingOutlined, RobotOutlined } from '@ant-design/icons';
import { Button, Checkbox, Input } from 'antd';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toAppError, useApi, useReliableWrite, type AiJob } from '@recruiter/api-client';

export const TASK_NAMES: Record<string, string> = {
  A1: '岗位画像与 JD 草稿',
  A2: '人才搜索建议',
  A3: '简历字段提取',
  A4: '沟通回复草稿',
  A5: '候选人证据评估',
  A6: '面试记录整理',
  A7: '岗位数据洞察',
};
const STATES: Record<string, { label: string; tone: string }> = {
  queued: { label: '排队中', tone: 'muted' },
  running: { label: '生成中', tone: 'ai' },
  retry: { label: '等待重试', tone: 'warning' },
  dead: { label: '执行失败', tone: 'danger' },
  review: { label: '待你复核', tone: 'ai' },
  applied: { label: '已执行', tone: 'success' },
  reviewed: { label: '已阅', tone: 'success' },
  cancelled: { label: '已取消', tone: 'muted' },
  rejected: { label: '未采纳', tone: 'muted' },
  shadow: { label: '影子结果', tone: 'muted' },
  deferred: { label: '等待可联系时段', tone: 'warning' },
};
const WORKING = new Set(['queued', 'running', 'retry']);
const VERDICT: Record<string, { label: string; tone: string }> = {
  meet: { label: '满足', tone: 'success' },
  not_meet: { label: '不满足', tone: 'danger' },
  unknown: { label: '缺证据', tone: 'warning' },
};
const CONCLUSION: Record<string, string> = {
  advance: '建议推进',
  reject: '建议淘汰',
  need_info: '信息不足，建议追问',
  hold: '存在风险，建议人工判断',
};
const FIELD: Record<string, string> = {
  must: '必备要求',
  plus: '加分项',
  redflag: '风险项',
  jd: 'JD',
  must_ask: '必问问题',
  city: '城市',
  company: '公司',
  title: '职位',
  school: '学校',
  degree: '学历',
  skills: '技能',
  experience: '经历',
  education: '教育',
  certificates: '证书',
  expected_city: '期望城市',
};

type Out = Record<string, unknown>;
const str = (v: unknown) => (typeof v === 'string' ? v : v == null ? '' : JSON.stringify(v));
const arr = (v: unknown) => (Array.isArray(v) ? v : []);

function Lines({ text }: { text: string }) {
  return <div className="as-pre">{text}</div>;
}

/** 按任务类型展示结果要点；完整证据在 AI 任务页 */
function JobOutput({ job }: { job: AiJob }) {
  const out = (job.output ?? {}) as Out;
  switch (job.component) {
    case 'A7':
      return (
        <>
          <Lines text={str(out.answer)} />
          {arr(out.suggestions).length > 0 && (
            <>
              <div className="as-sub">建议动作</div>
              <ol className="as-ol">
                {arr(out.suggestions).map((s, i) => (
                  <li key={i}>{str(s)}</li>
                ))}
              </ol>
            </>
          )}
        </>
      );
    case 'A4':
      return (
        <>
          <blockquote className="as-quote">{str(out.reply)}</blockquote>
          {out.needs_human === true && <p className="as-warn">AI 判断这条需要 HR 亲自处理。</p>}
        </>
      );
    case 'A2':
      return (
        <>
          <div className="as-chips">
            {arr(out.keywords).map((k) => (
              <span key={str(k)} className="as-chip">
                {str(k)}
              </span>
            ))}
          </div>
          {arr(out.city).length > 0 && <p>城市：{arr(out.city).map(str).join('、')}</p>}
          {arr(out.exclude_keywords).length > 0 && (
            <p>排除：{arr(out.exclude_keywords).map(str).join('、')}</p>
          )}
          {str(out.explanation) && <p className="as-muted">{str(out.explanation)}</p>}
        </>
      );
    case 'A5': {
      const criteria = arr((job.inputs as Out | undefined)?.criteria) as {
        id: string;
        text: string;
      }[];
      const text = (id: string) => criteria.find((c) => c.id === id)?.text ?? id;
      return (
        <>
          <p className="as-strong">
            {CONCLUSION[str(out.conclusion)] ?? str(out.conclusion)}
            {typeof out.score === 'number' && (
              <span className="as-muted"> · 参考分 {out.score}</span>
            )}
            {typeof out.confidence === 'number' && (
              <span className="as-muted"> · 把握度 {Math.round(out.confidence * 100)}%</span>
            )}
          </p>
          <ul className="as-criteria">
            {arr(out.items).map((raw) => {
              const it = raw as {
                id: string;
                verdict: string;
                note: string;
                evidence: { quote: string }[];
              };
              const v = VERDICT[it.verdict] ?? { label: it.verdict, tone: '' };
              return (
                <li key={it.id}>
                  <span className={`as-tag as-tone-${v.tone}`}>{v.label}</span>
                  <span>
                    {text(it.id)}
                    {it.evidence?.[0]?.quote && (
                      <mark className="as-evidence">“{it.evidence[0].quote}”</mark>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
          {arr(out.questions).length > 0 && (
            <>
              <div className="as-sub">建议追问</div>
              <ol className="as-ol">
                {arr(out.questions).map((q, i) => (
                  <li key={i}>{str(q)}</li>
                ))}
              </ol>
            </>
          )}
        </>
      );
    }
    case 'A3':
    case 'A1': {
      const fields = (out.fields ?? {}) as Record<string, unknown>;
      const entries = Object.entries(fields);
      if (!entries.length) return <p className="as-muted">没有提取到有原文依据的字段。</p>;
      return (
        <dl className="as-dl">
          {entries.map(([k, v]) => (
            <div key={k}>
              <dt>{FIELD[k] ?? k}</dt>
              <dd>
                <Lines text={typeof v === 'object' && v ? str((v as Out).value) : str(v)} />
              </dd>
            </div>
          ))}
          {arr(out.pending).length > 0 && (
            <div>
              <dt>待确认</dt>
              <dd>{arr(out.pending).map(str).join('；')}</dd>
            </div>
          )}
        </dl>
      );
    }
    case 'A6':
      return (
        <ul className="as-ol">
          {arr(out.items).map((raw, i) => {
            const it = raw as { id: string; notes: string };
            return (
              <li key={i}>
                <strong>{it.id}</strong>：{it.notes}
              </li>
            );
          })}
        </ul>
      );
    default:
      return <Lines text={JSON.stringify(out, null, 2)} />;
  }
}

/** 对话里的 AI 任务卡：生成中自动刷新；结果出来后可直接核对并确认 */
export function JobCard({ initial }: { initial: AiJob }) {
  const api = useApi();
  const [job, setJob] = useState(initial);
  const [error, setError] = useState('');
  const [verified, setVerified] = useState(false);
  const [reason, setReason] = useState('在 AI 助手中逐项核对了原文证据');

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const next = await api.aiJob(initial.id);
        if (alive) {
          setJob(next);
          setError('');
        }
      } catch (e) {
        if (alive) setError(toAppError(e).message);
      }
    };
    void tick();
    const timer = setInterval(() => {
      if (WORKING.has(job.status) || job.status === 'deferred') void tick();
    }, 2500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
    // 状态变化时重新决定是否继续轮询
  }, [api, initial.id, job.status]);

  const op = useReliableWrite(
    (body: { action: string; expected_version: number; reason: string; verified: boolean }, opts) =>
      api.aiJobCommand(job.id, body, opts),
    (next) => setJob(next),
  );

  const state = STATES[job.status] ?? { label: job.status, tone: 'muted' };
  const executes =
    ['A1', 'A3', 'A4'].includes(job.component) ||
    (job.component === 'A5' && ['advance', 'reject'].includes(str(job.output?.conclusion)));
  return (
    <div className="as-card as-card-ai" aria-label={`AI 任务 ${TASK_NAMES[job.component]}`}>
      <div className="as-card-h">
        <RobotOutlined aria-hidden className="as-ai-icon" />
        <span className="as-card-title">{TASK_NAMES[job.component] ?? job.component}</span>
        <span className={`as-tag as-tone-${state.tone}`} role="status">
          {WORKING.has(job.status) && <LoadingOutlined aria-hidden />} {state.label}
        </span>
      </div>
      {WORKING.has(job.status) && (
        <p className="as-muted">AI 正在根据原文生成建议，完成后会出现在这里，你可以先去做别的。</p>
      )}
      {job.status === 'dead' && (
        <p className="as-warn">
          任务没有成功（{job.error_code || '模型调用失败'}）。可在 AI 任务页重新排队。
        </p>
      )}
      {job.output && <JobOutput job={job} />}
      {job.status === 'review' && (
        <div className="as-review">
          <Input
            aria-label="复核说明"
            value={reason}
            maxLength={1000}
            onChange={(e) => setReason(e.target.value)}
            disabled={op.locked}
          />
          <Checkbox
            checked={verified}
            onChange={(e) => setVerified(e.target.checked)}
            disabled={op.locked}
          >
            我已核对原文、证据和当前状态
          </Checkbox>
          <div className="as-actions">
            <Button
              type="primary"
              disabled={op.locked || !verified || !reason.trim()}
              loading={op.busy}
              onClick={() =>
                void op.submit({
                  action: 'approve',
                  expected_version: job.version,
                  reason,
                  verified,
                })
              }
            >
              {executes ? '确认并执行' : '确认已阅'}
            </Button>
            <Button
              disabled={op.locked || !reason.trim()}
              onClick={() =>
                void op.submit({
                  action: 'reject',
                  expected_version: job.version,
                  reason,
                  verified,
                })
              }
            >
              不采纳
            </Button>
          </div>
          {op.error && (
            <p role="alert" className="as-error">
              {op.error}
            </p>
          )}
          {op.retry && (
            <Button size="small" onClick={op.retryAction}>
              重试同一次提交
            </Button>
          )}
        </div>
      )}
      {['applied', 'reviewed', 'rejected'].includes(job.status) && (
        <p className={job.status === 'rejected' ? 'as-muted' : 'as-ok'}>
          {job.status !== 'rejected' && <CheckCircleFilled aria-hidden />}{' '}
          {job.status === 'rejected' ? '已标记为不采纳' : '已处理'}
        </p>
      )}
      {error && (
        <p role="alert" className="as-error">
          {error}
        </p>
      )}
      <Link className="as-link" to={`/ai-jobs?job=${encodeURIComponent(job.id)}`}>
        查看完整证据与执行记录
      </Link>
    </div>
  );
}
