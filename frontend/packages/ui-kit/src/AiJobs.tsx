import { useEffect, useRef, useState } from 'react';
import { useApi, useReliableWrite, type AiIntent, type AiJob } from '@recruiter/api-client';
import { useLiveData } from './LiveHiring';

const names: Record<string, string> = {
  A1: '岗位画像与 JD 草稿',
  A2: '人才搜索建议',
  A3: '简历字段提取',
  A4: '沟通回复草稿',
  A5: '候选人证据评估',
  A6: '面试记录整理',
  A7: '岗位数据洞察',
};
const states: Record<string, string> = {
  queued: '排队中',
  running: '生成中',
  retry: '等待重试',
  dead: '执行失败',
  review: '待人工复核',
  applied: '已执行',
  reviewed: '已阅建议',
  cancelled: '已取消',
  rejected: '未采纳',
  shadow: '影子结果 · 仅供观察',
  deferred: '等待可联系时段',
};
const box = {
  background: '#fff',
  padding: 16,
  marginBlock: 16,
  border: '1px solid #dfe5ec',
  borderRadius: 10,
};
const input = {
  display: 'block',
  width: '100%',
  boxSizing: 'border-box' as const,
  padding: 10,
  marginBlock: 8,
  fontSize: 16,
  border: '1px solid #cbd5e1',
  borderRadius: 6,
};

function TargetPicker({
  component,
  value,
  change,
  disabled,
}: {
  component: string;
  value: string;
  change: (id: string) => void;
  disabled: boolean;
}) {
  const api = useApi();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [position, setPosition] = useState('');
  const isPosition = ['A1', 'A2', 'A7'].includes(component) || (component === 'A5' && !position);
  const options = useLiveData(JSON.stringify([component, search, page, position]), async () => {
    if (isPosition) {
      const rows = await api.positionPage(page, '', { query: search });
      return {
        ...rows,
        items: rows.items.filter((p) => p.canEdit).map((p) => ({ id: p.id, name: p.name })),
      };
    }
    if (component === 'A5') {
      const rows = await api.livePositionApplications(position);
      const items = rows
        .filter((a) => a.can_edit && !a.outcome && a.stage === 'ai_eval')
        .map((a) => ({ id: a.id, name: `${a.candidate_name} · ${a.position_name}` }));
      return { items, total: items.length };
    }
    if (component === 'A6') {
      const rows = await api.liveInterviews(page, { mine: 'true' });
      return {
        ...rows,
        items: rows.items.map((iv) => ({
          id: iv.id,
          name: `${iv.candidate_name} · ${iv.round_name}`,
        })),
      };
    }
    const rows = await api.candidatePage(page, { query: search });
    return {
      ...rows,
      items: rows.items
        .filter((c) => c.consent === 'granted' && !c.do_not_contact)
        .map((c) => ({ id: c.id, name: c.profile.name })),
    };
  });
  const label = isPosition
    ? '选择岗位'
    : component === 'A5'
      ? '选择待评估应聘记录'
      : component === 'A6'
        ? '选择本人面试'
        : '选择候选人';
  return (
    <fieldset disabled={disabled} style={{ border: 0, padding: 0 }}>
      {!['A5', 'A6'].includes(component) && (
        <label>
          搜索对象
          <input
            style={input}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </label>
      )}
      <label>
        {label}
        <select
          aria-label={label}
          required={!(component === 'A5' && value && !position)}
          style={input}
          value={component === 'A5' && !position ? '' : value}
          onChange={(e) => {
            if (component === 'A5' && !position) {
              setPosition(e.target.value);
              change('');
            } else change(e.target.value);
          }}
        >
          <option value="">请选择</option>
          {value &&
            !options.data?.items.some((p) => p.id === value) &&
            !(component === 'A5' && !position) && <option value={value}>从详情页选择的对象</option>}
          {options.data?.items.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {component === 'A5' && value && !position && (
        <p>已选中详情页的应聘记录，可直接创建任务，或重新选择岗位。</p>
      )}
      {component === 'A5' && position && (
        <button
          type="button"
          onClick={() => {
            setPosition('');
            change('');
          }}
        >
          重新选择岗位
        </button>
      )}
      {options.error && <p role="alert">{options.error}</p>}
      {(component !== 'A5' || !position) && (
        <div>
          <button type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>
            上一组对象
          </button>{' '}
          第 {page} 页{' '}
          <button
            type="button"
            disabled={page * 20 >= (options.data?.total ?? 0)}
            onClick={() => setPage(page + 1)}
          >
            下一组对象
          </button>
        </div>
      )}
    </fieldset>
  );
}

function JsonView({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span>暂无结果</span>;
  if (typeof value !== 'object')
    return (
      <span style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{String(value)}</span>
    );
  if (Array.isArray(value))
    return (
      <ul>
        {value.map((item, i) => (
          <li key={i}>
            <JsonView value={item} />
          </li>
        ))}
      </ul>
    );
  const labels: Record<string, string> = {
    fields: '建议字段',
    value: '提取内容',
    evidence: '原文证据',
    ref: '来源编号',
    quote: '引用原文',
    source: '来源类型',
    skills: '技能',
    experience: '经历',
    education: '教育',
    items: '评估条目',
    verdict: '判断',
    note: '说明',
    conclusion: '建议',
    score: '参考分',
    confidence: '把握度',
    reply: '回复草稿',
    claims: '引用依据',
    questions: '待补充问题',
    answer: '分析',
    suggestions: '建议',
    data_refs: '数据来源',
    notes: '面试记录',
    self_confidence: '模型自评',
    invalid_evidence: '无效引用数',
    sensitive: '敏感内容',
    coverage: '证据覆盖率',
    sample_conclusions: '多次评估结论',
    pending: '待确认事项',
    cited: '引用数据',
    dropped: '已剔除（证据不符）',
    field: '字段',
    reason: '原因',
  };
  return (
    <dl>
      {Object.entries(value).map(([key, item]) => (
        <div key={key} style={{ marginBlock: 8 }}>
          <dt>
            <strong>{labels[key] ?? key}</strong>
          </dt>
          <dd style={{ marginInlineStart: 16 }}>
            <JsonView value={item} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Review({ job, refresh }: { job: AiJob; refresh: (job: AiJob) => void }) {
  const api = useApi();
  const [reason, setReason] = useState('');
  const [verified, setVerified] = useState(false);
  const op = useReliableWrite(
    (body: { action: string; expected_version: number; reason: string; verified: boolean }, opts) =>
      api.aiJobCommand(job.id, body, opts),
    refresh,
  );
  const submit = (action: string) =>
    void op.submit({ action, expected_version: job.version, reason, verified });
  return (
    <section style={box}>
      <h2>
        {names[job.component]} · {states[job.status] ?? job.status}
      </h2>
      <p>
        任务 {job.id} · 尝试 {job.attempts} 次
      </p>
      {job.error_code && (
        <p role="status">任务暂未完成：{job.error_code}。请核对配置或重新生成。</p>
      )}
      <JsonView value={job.output} />
      <details>
        <summary>核对输入与原文证据</summary>
        <JsonView value={job.inputs} />
      </details>
      <details>
        <summary>执行记录</summary>
        {job.history?.map((h, i) => (
          <p key={i}>
            {new Date(h.at).toLocaleString()} · {states[h.status] ?? h.status} {h.code}
          </p>
        ))}
        <p>
          模型调用 {job.runs?.length ?? 0} 次 · token 总计{' '}
          {job.runs?.reduce((n, r) => n + r.tokens, 0) ?? 0}
        </p>
      </details>
      {['review', 'dead', 'queued', 'running', 'retry', 'deferred'].includes(job.status) && (
        <>
          <label>
            处理说明
            <textarea
              style={input}
              maxLength={1000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              disabled={op.locked}
            />
          </label>
          {job.status === 'review' && (
            <label>
              <input
                type="checkbox"
                checked={verified}
                onChange={(e) => setVerified(e.target.checked)}
                disabled={op.locked}
              />
              我已核对原文、证据和当前状态
            </label>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 12 }}>
            {job.status === 'review' && (
              <>
                <button
                  disabled={op.locked || !verified || !reason.trim()}
                  onClick={() => submit('approve')}
                >
                  {['A2', 'A6', 'A7'].includes(job.component) ||
                  (job.component === 'A5' &&
                    !['advance', 'reject'].includes(String(job.output?.conclusion)))
                    ? '确认已阅建议'
                    : '确认并执行'}
                </button>
                <button disabled={op.locked || !reason.trim()} onClick={() => submit('reject')}>
                  不采纳
                </button>
              </>
            )}
            {job.status === 'dead' ? (
              <button disabled={op.locked || !reason.trim()} onClick={() => submit('retry')}>
                重新排队
              </button>
            ) : (
              <button disabled={op.locked || !reason.trim()} onClick={() => submit('cancel')}>
                取消任务
              </button>
            )}
          </div>
          {op.error && <p role="alert">{op.error}</p>}
          {op.retry && (
            <button onClick={op.retryAction} disabled={op.busy}>
              重试同一次提交
            </button>
          )}
          {op.conflict && (
            <button
              onClick={() =>
                void api.aiJob(job.id).then((j) => {
                  refresh(j);
                  op.refreshed();
                })
              }
            >
              刷新后重新核对
            </button>
          )}
        </>
      )}
      {job.component === 'A6' && <p>记录整理供面试官参考，请在面评页独立评分并提交。</p>}
    </section>
  );
}

const EXAMPLES = ['白班客服还差几个人', '评估一下张三是否符合客服专员', '帮客服专员写一版 JD'];

/** 一句话让 AI 做事：后端识别任务和对象；对象唯一时直接开始，否则给出可选项。 */
function AskPanel({ initial, onStarted }: { initial?: string; onStarted: (job: AiJob) => void }) {
  const api = useApi();
  const [text, setText] = useState(initial ?? '');
  const [result, setResult] = useState<AiIntent>();
  const ask = useReliableWrite(
    (body: { text: string }, opts) => api.askAi(body, opts),
    (r) => {
      setResult(r);
      if (r.job) onStarted(r.job);
    },
  );
  const pick = useReliableWrite(
    (body: { component: string; object_id: string; prompt: string; label: string }, opts) =>
      api.startAiJob(
        { component: body.component, object_id: body.object_id, prompt: body.prompt },
        opts,
      ),
    (job) => {
      setResult((r) =>
        r
          ? {
              ...r,
              status: 'started',
              options: [],
              message: `已开始“${names[job.component]}”。结果生成后请核对原文证据再确认。`,
            }
          : r,
      );
      onStarted(job);
    },
  );
  const fired = useRef(false);
  useEffect(() => {
    if (initial?.trim() && !fired.current) {
      fired.current = true;
      void ask.submit({ text: initial.trim() });
    }
    // 只在打开时执行一次从指令栏带来的指令
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const busy = ask.locked || pick.locked;
  const examples = result?.examples.length ? result.examples : EXAMPLES;
  return (
    <form
      style={{ ...box, borderColor: '#b9c8f5' }}
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) {
          setResult(undefined);
          void ask.submit({ text: text.trim() });
        }
      }}
    >
      <label>
        <strong>用一句话让 AI 做事</strong>
        <textarea
          style={input}
          rows={2}
          maxLength={4000}
          value={text}
          disabled={busy}
          placeholder="比如：白班客服还差几个人？/ 评估一下张三 / 帮客服专员写一版 JD"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />
      </label>
      <button disabled={busy || !text.trim()}>{ask.busy ? 'AI 正在理解…' : '交给 AI'}</button>
      {(!result || result.status === 'unsupported') && (
        <p style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          可以这样说：
          {examples.map((x) => (
            <button key={x} type="button" disabled={busy} onClick={() => setText(x)}>
              {x}
            </button>
          ))}
        </p>
      )}
      {result && (
        <div role="status" aria-live="polite" style={{ marginTop: 12 }}>
          {result.component && (
            <p>
              识别为：<strong>{result.component_name}</strong>
              {result.router === 'rules' ? '（按关键词识别）' : ''}
            </p>
          )}
          <p>{result.message}</p>
          {result.status === 'choose' && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {result.options.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void pick.submit({
                      component: result.component ?? '',
                      object_id: o.id,
                      prompt: result.prompt,
                      label: o.label,
                    })
                  }
                >
                  {o.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {(ask.error || pick.error) && <p role="alert">{ask.error || pick.error}</p>}
      {(ask.retry || pick.retry) && (
        <button
          type="button"
          onClick={ask.retry ? ask.retryAction : pick.retryAction}
          disabled={ask.busy || pick.busy}
        >
          重试同一次提交
        </button>
      )}
    </form>
  );
}

export function AiJobs({ business = false, ask }: { business?: boolean; ask?: string }) {
  const api = useApi();
  const query = new URLSearchParams(window.location.search);
  const [component, setComponent] = useState(business ? 'A6' : (query.get('component') ?? 'A3'));
  const [objectId, setObjectId] = useState(query.get('object') ?? '');
  const [prompt, setPrompt] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState('');
  const health = useLiveData('ai-health', () => api.aiHealth());
  const jobs = useLiveData(String(page), () => api.aiJobs(page));
  const detail = useLiveData(selected, async () => (selected ? api.aiJob(selected) : undefined));
  const start = useReliableWrite(
    (body: { component: string; object_id: string; prompt: string }, opts) =>
      api.startAiJob(body, opts),
    (job) => {
      setSelected(job.id);
      void jobs.refresh();
    },
  );
  const configured = health.data?.components[component] && health.data?.enabled[component];
  return (
    <main style={{ maxWidth: 1000, padding: 16, margin: 'auto' }}>
      <h1>AI 任务与复核</h1>
      <p>生成建议后核对原文。影子模式只记录结果；录用决定和面试评分由对应负责人完成。</p>
      {health.error && <p role="alert">{health.error}</p>}
      {health.data && (
        <p role="status">
          当前模式：
          {
            (
              { manual: '人工', shadow: '影子观察', normal: '按策略执行' } as Record<string, string>
            )[health.data.mode]
          }
          。{!configured && '当前组件尚未启用或 Dify 未配置。'}
          {!health.data.worker_enabled && '后台自动执行未开启。'}
        </p>
      )}
      {!business && (
        <AskPanel
          initial={ask}
          onStarted={(job) => {
            setSelected(job.id);
            void jobs.refresh();
          }}
        />
      )}
      <details open={business || !!query.get('object')} style={{ marginBlock: 16 }}>
        {!business && (
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>或手动选择任务和对象</summary>
        )}
        <form
          style={box}
          onSubmit={(e) => {
            e.preventDefault();
            void start.submit({ component, object_id: objectId, prompt });
          }}
        >
          <label>
            任务类型
            <select
              style={input}
              value={component}
              disabled={start.locked || business}
              onChange={(e) => {
                setComponent(e.target.value);
                setObjectId('');
              }}
            >
              {Object.entries(names).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <TargetPicker
            key={component}
            component={component}
            value={objectId}
            change={setObjectId}
            disabled={start.locked}
          />
          <label>
            {component === 'A6' ? '已获授权的面试原始记录' : '补充说明（可选）'}
            <textarea
              style={input}
              value={prompt}
              maxLength={8000}
              rows={4}
              disabled={start.locked}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </label>
          <button disabled={start.locked || !configured || !objectId.trim()}>创建 AI 任务</button>
          {start.error && <p role="alert">{start.error}</p>}
          {start.retry && (
            <button type="button" onClick={start.retryAction} disabled={start.busy}>
              重试同一次提交
            </button>
          )}
        </form>
      </details>
      {detail.error && <p role="alert">{detail.error}</p>}
      {detail.data && (
        <Review
          key={detail.data.id}
          job={detail.data}
          refresh={(j) => {
            detail.update(j);
            void jobs.refresh();
          }}
        />
      )}
      <h2>可见任务</h2>
      {jobs.error && <p role="alert">{jobs.error}</p>}
      {jobs.data?.total === 0 && <p>暂无任务。从岗位、候选人或面试详情可发起对应任务。</p>}
      {jobs.data?.items.map((job) => (
        <article style={box} key={job.id}>
          <button onClick={() => setSelected(job.id)}>
            {names[job.component]} · {states[job.status] ?? job.status}
          </button>
          <p style={{ overflowWrap: 'anywhere' }}>
            {job.object_id} · {new Date(job.created_at).toLocaleString()}
          </p>
        </article>
      ))}
      <button disabled={page === 1} onClick={() => setPage(page - 1)}>
        上一页
      </button>{' '}
      第 {page} 页{' '}
      <button disabled={page * 20 >= (jobs.data?.total ?? 0)} onClick={() => setPage(page + 1)}>
        下一页
      </button>
    </main>
  );
}
