import { ActionButton } from './controls';
import { Select } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useApi, useReliableWrite, type AiIntent, type AiJob } from '@recruiter/api-client';
import { useLiveData } from './LiveHiring';

const names: Record<string, string> = {
  A1: '岗位画像与 JD 草稿',
  A2: '简历匹配与人才搜索',
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
  background: 'var(--rc-surface)',
  padding: 16,
  marginBlock: 16,
  border: '1px solid var(--rc-line)',
  borderRadius: 16,
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
        <ActionButton
          type="button"
          onClick={() => {
            setPosition('');
            change('');
          }}
        >
          重新选择岗位
        </ActionButton>
      )}
      {options.error && <p role="alert">{options.error}</p>}
      {(component !== 'A5' || !position) && (
        <div>
          <ActionButton type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>
            上一组对象
          </ActionButton>{' '}
          第 {page} 页{' '}
          <ActionButton
            type="button"
            disabled={page * 20 >= (options.data?.total ?? 0)}
            onClick={() => setPage(page + 1)}
          >
            下一组对象
          </ActionButton>
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
    id: '条目',
    kb_ref: '知识来源',
    intents: '识别意图',
    needs_human: '需要人工处理',
    keywords: '搜索关键词',
    exclude: '排除词',
    city: '城市',
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

type ResumeMatch = {
  candidate_id: string;
  score: number;
  coverage: number;
  conclusion: string;
  items: {
    id: string;
    verdict: string;
    note: string;
    evidence: { ref: string; quote: string }[];
  }[];
  questions: string[];
};

export function MatchingResults({ job }: { job: AiJob }) {
  const api = useApi();
  const matches = (job.output?.matches ?? []) as ResumeMatch[];
  const people = useLiveData(job.id, async () =>
    Object.fromEntries(
      await Promise.all(
        matches.map(async (m) => {
          try {
            return [m.candidate_id, (await api.candidateRecord(m.candidate_id)).profile.name];
          } catch {
            return [m.candidate_id, m.candidate_id];
          }
        }),
      ),
    ),
  );
  const criteria = (job.inputs?.criteria ?? []) as { id: string; text: string }[];
  return (
    <section aria-label="简历匹配结果">
      <h3>简历匹配结果 · {matches.length} 人</h3>
      <p>
        仅比较本次选中的已授权资料，每次最多 5 人、每份资料最多 6000
        字。参考分由核验后的岗位条目计算，缺少证据不代表不符合要求，需人工核实。
      </p>
      {!matches.length && <p>本次没有可匹配的已授权候选人；下方仅为人才搜索建议。</p>}
      {matches.map((m) => (
        <article key={m.candidate_id} style={box}>
          <h4>
            <a href={`/candidates/${encodeURIComponent(m.candidate_id)}`}>
              {people.data?.[m.candidate_id] ?? m.candidate_id}
            </a>{' '}
            · 参考分 {m.score}
          </h4>
          <p>
            证据覆盖率 {Math.round(m.coverage * 100)}% ·{' '}
            {{
              advance: '现有证据符合必备项',
              reject: '存在不符合项，需核实',
              need_info: '资料不足，建议补充',
              hold: '存在待核实风险',
            }[m.conclusion] ?? '请核实'}
          </p>
          {m.items.map((item) => (
            <div key={item.id} style={{ marginBlock: 12 }}>
              <strong>
                {criteria.find((c) => c.id === item.id)?.text ?? item.id} ·{' '}
                {{ meet: '有依据支持', not_meet: '有不符合证据', unknown: '待补充证据' }[
                  item.verdict
                ] ?? item.verdict}
              </strong>
              <p>{item.note}</p>
              {item.evidence.map((e, i) => (
                <blockquote key={i}>
                  {e.quote}
                  <small>（来源 {e.ref}）</small>
                </blockquote>
              ))}
            </div>
          ))}
          {!!m.questions.length && <p>建议追问：{m.questions.join('；')}</p>}
          <a href={`/candidates/${encodeURIComponent(m.candidate_id)}`}>查看候选人并人工关联岗位</a>
        </article>
      ))}
      <details>
        <summary>人才搜索建议</summary>
        <JsonView
          value={{ keywords: job.output?.keywords, explanation: job.output?.explanation }}
        />
      </details>
    </section>
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
      {job.component === 'A2' && job.output ? (
        <MatchingResults key={job.id + job.version} job={job} />
      ) : (
        <JsonView value={job.output} />
      )}
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
                <ActionButton
                  disabled={op.locked || !verified || !reason.trim()}
                  onClick={() => submit('approve')}
                >
                  {['A2', 'A6', 'A7'].includes(job.component) ||
                  (job.component === 'A5' &&
                    !['advance', 'reject'].includes(String(job.output?.conclusion)))
                    ? '确认已阅建议'
                    : '确认并执行'}
                </ActionButton>
                <ActionButton
                  disabled={op.locked || !reason.trim()}
                  onClick={() => submit('reject')}
                >
                  不采纳
                </ActionButton>
              </>
            )}
            {job.status === 'dead' ? (
              <ActionButton disabled={op.locked || !reason.trim()} onClick={() => submit('retry')}>
                重新排队
              </ActionButton>
            ) : (
              <ActionButton disabled={op.locked || !reason.trim()} onClick={() => submit('cancel')}>
                取消任务
              </ActionButton>
            )}
          </div>
          {op.error && <p role="alert">{op.error}</p>}
          {op.retry && (
            <ActionButton onClick={op.retryAction} disabled={op.busy}>
              重试同一次提交
            </ActionButton>
          )}
          {op.conflict && (
            <ActionButton
              onClick={() =>
                void api.aiJob(job.id).then((j) => {
                  refresh(j);
                  op.refreshed();
                })
              }
            >
              刷新后重新核对
            </ActionButton>
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
      <ActionButton disabled={busy || !text.trim()}>
        {ask.busy ? 'AI 正在理解…' : '交给 AI'}
      </ActionButton>
      {(!result || result.status === 'unsupported') && (
        <p style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          可以这样说：
          {examples.map((x) => (
            <ActionButton key={x} type="button" disabled={busy} onClick={() => setText(x)}>
              {x}
            </ActionButton>
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
                <ActionButton
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
                </ActionButton>
              ))}
            </div>
          )}
        </div>
      )}
      {(ask.error || pick.error) && <p role="alert">{ask.error || pick.error}</p>}
      {(ask.retry || pick.retry) && (
        <ActionButton
          type="button"
          onClick={ask.retry ? ask.retryAction : pick.retryAction}
          disabled={ask.busy || pick.busy}
        >
          重试同一次提交
        </ActionButton>
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
  const [candidateIds, setCandidateIds] = useState<string[]>([]);
  const [candidateSearch, setCandidateSearch] = useState('');
  const candidates = useLiveData(JSON.stringify([component, candidateSearch]), async () =>
    component === 'A2' ? api.candidatePage(1, { query: candidateSearch }) : undefined,
  );
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(query.get('job') ?? '');
  const health = useLiveData('ai-health', () => api.aiHealth());
  const jobs = useLiveData(String(page), () => api.aiJobs(page));
  const detail = useLiveData(selected, async () => (selected ? api.aiJob(selected) : undefined));
  const start = useReliableWrite(
    (
      body: { component: string; object_id: string; prompt: string; candidate_ids?: string[] },
      opts,
    ) => api.startAiJob(body, opts),
    (job) => {
      setSelected(job.id);
      void jobs.refresh();
    },
  );
  const configured = health.data?.components[component] && health.data?.enabled[component];
  return (
    <main className="rc-ai-workspace">
      <span className="rc-eyebrow">AI STUDIO · 人机协作</span>
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
            void start.submit({
              component,
              object_id: objectId,
              prompt,
              ...(component === 'A2' && candidateIds.length ? { candidate_ids: candidateIds } : {}),
            });
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
          {component === 'A2' && (
            <div style={{ marginBlock: 16 }}>
              <label htmlFor="matching-candidates">选择匹配简历（最多 5 人）</label>
              <Select
                id="matching-candidates"
                mode="multiple"
                showSearch
                filterOption={false}
                style={{ width: '100%' }}
                value={candidateIds}
                disabled={start.locked}
                onSearch={setCandidateSearch}
                onChange={(ids) => {
                  if (ids.length <= 5) setCandidateIds(ids);
                }}
                options={(candidates.data?.items ?? [])
                  .filter((c) => c.consent === 'granted' && !c.do_not_contact)
                  .map((c) => ({ value: c.id, label: c.profile.name }))}
              />
              <p>
                搜索姓名选择本次匹配对象。留空时匹配最近创建的最多 5
                位可见且已授权候选人；不会自动关联岗位或改变应聘状态。
              </p>
              {candidates.error && <p role="alert">{candidates.error}</p>}
            </div>
          )}
          <ActionButton type="submit" disabled={start.locked || !configured || !objectId.trim()}>
            创建 AI 任务
          </ActionButton>
          {start.error && <p role="alert">{start.error}</p>}
          {start.retry && (
            <ActionButton type="button" onClick={start.retryAction} disabled={start.busy}>
              重试同一次提交
            </ActionButton>
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
          <ActionButton onClick={() => setSelected(job.id)}>
            {names[job.component]} · {states[job.status] ?? job.status}
          </ActionButton>
          <p style={{ overflowWrap: 'anywhere' }}>
            {job.object_id} · {new Date(job.created_at).toLocaleString()}
          </p>
        </article>
      ))}
      <ActionButton disabled={page === 1} onClick={() => setPage(page - 1)}>
        上一页
      </ActionButton>{' '}
      第 {page} 页{' '}
      <ActionButton
        disabled={page * 20 >= (jobs.data?.total ?? 0)}
        onClick={() => setPage(page + 1)}
      >
        下一页
      </ActionButton>
    </main>
  );
}
