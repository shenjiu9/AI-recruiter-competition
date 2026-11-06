import { useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Button, NavBar, TextArea } from 'antd-mobile';
import { useQuery } from '@tanstack/react-query';
import {
  useApi,
  newIdempotencyKey,
  toAppError,
  type PositionCommand,
  type LivePosition,
} from '@recruiter/api-client';
import { POSITION_STATUS_LABEL } from '@recruiter/domain';
import { PositionCandidates } from './PositionCandidates';

export function PositionsPage() {
  const api = useApi();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['biz-positions', page],
    queryFn: () => api.positionPage(page, '', { view: 'participating' }),
    refetchInterval: 5000,
  });
  return (
    <main>
      <NavBar back={null}>我参与的岗位</NavBar>
      <div className="rm-card">
        <Link to="/">返回招聘待办</Link>
        {query.isError && <p role="alert">{toAppError(query.error).message}</p>}
        {query.data?.items.map((p) => (
          <article key={p.id} style={{ padding: '12px 0', borderBottom: '1px solid #ddd' }}>
            <Link to={`/positions/${p.id}`}>
              {p.name} · {POSITION_STATUS_LABEL[p.status]}
            </Link>
            <p>
              {p.dept} · {p.planned} 人 · {p.ownerHr}
            </p>
            {!p.profile.confirmedBy && <p>待确认画像：第 {p.profile.version} 版</p>}
            {p.closeRequest && <p>待确认关闭：{p.closeRequest.reason}</p>}
          </article>
        ))}
        <Button disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
          上一页
        </Button>
        <span> 第 {page} 页 </span>
        <Button
          disabled={page * 20 >= (query.data?.total ?? 0)}
          onClick={() => setPage((p) => p + 1)}
        >
          下一页
        </Button>
      </div>
    </main>
  );
}

function Decision({ pos, onDone }: { pos: LivePosition; onDone: () => void }) {
  const api = useApi();
  const [reason, setReason] = useState('');
  const [content, setContent] = useState('');
  const [source, setSource] = useState('');
  const [disclosure, setDisclosure] = useState<PositionCommand['disclosure']>('internal');
  const [profile, setProfile] = useState({
    must: pos.profile.must,
    plus: pos.profile.plus,
    redflag: pos.profile.redflag,
    must_ask: pos.profile.must_ask,
  });
  const [weights, setWeights] = useState(pos.profile.plus_weights);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  const [conflict, setConflict] = useState(false);
  const pending = useRef<{ body: PositionCommand; key: string }>();
  const submit = async (action: PositionCommand['action']) => {
    if (busy || conflict) return;
    pending.current ??= {
      body: {
        action,
        expected_version: pos.version,
        reason,
        content,
        source,
        disclosure,
        ...(action === 'amend_confirm_profile'
          ? {
              ...profile,
              jd: pos.jd.content,
              plus_weights: profile.plus
                .split('\n')
                .filter((s) => s.trim())
                .map((_, i) => weights[i] ?? 'medium'),
            }
          : {}),
      },
      key: newIdempotencyKey(),
    };
    setBusy(true);
    setError('');
    try {
      await api.positionCommand(pos.id, pending.current.body, {
        idempotencyKey: pending.current.key,
      });
      pending.current = undefined;
      setRetry(false);
      onDone();
    } catch (e) {
      const err = toAppError(e);
      const uncertain = err.status === 0 || err.status >= 500;
      setRetry(uncertain);
      setConflict(err.status === 409);
      if (!uncertain) pending.current = undefined;
      setError(err.message + (err.status === 409 ? '。输入已保留，请刷新后核对。' : ''));
    } finally {
      setBusy(false);
    }
  };
  const locked = busy || retry || conflict;
  return (
    <div className="rm-card">
      {pos.canConfirm && !pos.profile.confirmedBy && (
        <Button color="primary" disabled={locked} onClick={() => void submit('confirm_profile')}>
          确认第 {pos.profile.version} 版画像
        </Button>
      )}
      {pos.canConfirm && (
        <details>
          <summary>修改并确认画像</summary>
          {(['must', 'plus', 'redflag', 'must_ask'] as const).map((key, i) => (
            <label key={key} style={{ display: 'block', margin: '12px 0' }}>
              {['修改必备条件', '修改加分项', '修改不合适信号', '修改必问项'][i]}
              <textarea
                aria-label={['修改必备条件', '修改加分项', '修改不合适信号', '修改必问项'][i]}
                value={profile[key]}
                maxLength={2000}
                disabled={locked}
                style={{ width: '100%', boxSizing: 'border-box', minHeight: 72 }}
                onChange={(e) => setProfile((p) => ({ ...p, [key]: e.target.value }))}
              />
            </label>
          ))}
          {profile.plus
            .split('\n')
            .filter((s) => s.trim())
            .map((text, i) => (
              <label key={i} style={{ display: 'block', margin: '8px 0' }}>
                {text} 权重{' '}
                <select
                  disabled={locked}
                  value={weights[i] ?? 'medium'}
                  onChange={(e) =>
                    setWeights((values) => {
                      const next = [...values];
                      next[i] = e.target.value as 'high' | 'medium' | 'low';
                      return next;
                    })
                  }
                >
                  <option value="high">高</option>
                  <option value="medium">中</option>
                  <option value="low">低</option>
                </select>
              </label>
            ))}
          <p>保存为新版本并立即确认生效；按打开页面时的岗位版本校验。</p>
          <Button
            color="primary"
            disabled={locked}
            onClick={() => void submit('amend_confirm_profile')}
          >
            保存修改并确认
          </Button>
        </details>
      )}
      {pos.closeRequest && pos.canConfirm && (
        <section>
          <h2>关闭确认</h2>
          <p>申请原因：{pos.closeRequest.reason}</p>
          <p>确认后岗位停止招聘，并释放未使用编制预占。</p>
          <TextArea
            aria-label="关闭驳回原因"
            placeholder="驳回时填写原因"
            value={reason}
            disabled={locked}
            maxLength={500}
            onChange={setReason}
          />
          <Button color="danger" disabled={locked} onClick={() => void submit('confirm_close')}>
            确认关闭岗位
          </Button>
          <Button disabled={locked} onClick={() => void submit('reject_close')}>
            驳回关闭申请
          </Button>
        </section>
      )}
      {pos.canCollaborate && (
        <section>
          <h2>补充知识库</h2>
          <label>
            知识内容
            <TextArea value={content} disabled={locked} maxLength={4000} onChange={setContent} />
          </label>
          <label>
            知识来源
            <TextArea value={source} disabled={locked} maxLength={300} onChange={setSource} />
          </label>
          <label>
            披露级别{' '}
            <select
              aria-label="披露级别"
              disabled={locked}
              value={disclosure}
              onChange={(e) => setDisclosure(e.target.value as PositionCommand['disclosure'])}
            >
              <option value="proactive">可主动说</option>
              <option value="asked">被问到可说</option>
              <option value="internal">仅内部参考</option>
              <option value="handoff">转人工</option>
            </select>
          </label>
          <Button disabled={locked} onClick={() => void submit('save_kb')}>
            保存知识条目
          </Button>
        </section>
      )}
      {error && (
        <p role="alert" style={{ color: '#b42318' }}>
          {error}
        </p>
      )}
      {retry && (
        <Button loading={busy} onClick={() => void submit(pending.current!.body.action)}>
          重试本次操作
        </Button>
      )}
      {conflict && <Button onClick={onDone}>刷新并重新核对</Button>}
    </div>
  );
}

export function PositionReviewPage() {
  const { id = '' } = useParams();
  const api = useApi();
  const [revision, setRevision] = useState(0);
  const query = useQuery({
    queryKey: ['biz-position', id, revision],
    queryFn: () => api.positionDetail(id),
  });
  const p = query.data;
  return (
    <main>
      <NavBar back={null}>岗位确认</NavBar>
      <div className="rm-card">
        <Link to="/positions">返回岗位列表</Link>
        {query.isPending && <p role="status">正在加载岗位…</p>}
        {query.isError && <p role="alert">{toAppError(query.error).message}</p>}
        {p && (
          <>
            <h1 style={{ fontSize: 22, overflowWrap: 'anywhere' }}>{p.name}</h1>
            <p>
              {POSITION_STATUS_LABEL[p.status]} · {p.dept} · {p.planned} 人
            </p>
            <h2>第 {p.profile.version} 版画像</h2>
            <p>{p.profile.confirmedBy ? '画像已确认' : '等待确认'}</p>
            <p>当前生效：{p.activeProfile ? `第 ${p.activeProfile.version} 版` : '尚无生效版本'}</p>
            <h3>必备条件</h3>
            <p style={{ whiteSpace: 'pre-wrap' }}>{p.profile.must}</p>
            <h3>加分项</h3>
            <p style={{ whiteSpace: 'pre-wrap' }}>
              {p.profile.plus
                .split('\n')
                .filter(Boolean)
                .map(
                  (s, i) =>
                    `${s}（${{ high: '高', medium: '中', low: '低' }[p.profile.plus_weights[i] ?? 'medium']}）`,
                )
                .join('\n') || '未填写'}
            </p>
            <h3>不合适信号</h3>
            <p>{p.profile.redflag || '未填写'}</p>
            <h3>必问项</h3>
            <p>{p.profile.must_ask || '未填写'}</p>
            <h3>JD 职责</h3>
            <p style={{ whiteSpace: 'pre-wrap' }}>{p.jd.content}</p>
            <details>
              <summary>画像历史</summary>
              {p.profiles.map((v) => (
                <article key={v.version}>
                  <strong>第 {v.version} 版</strong>
                  <p>{v.must}</p>
                  <p>{v.plus}</p>
                  <p>{v.redflag}</p>
                </article>
              ))}
            </details>
            <h2>岗位知识</h2>
            {p.knowledge
              .filter((e) => e.active)
              .map((e) => (
                <article key={e.id}>
                  <p>{e.content}</p>
                  <small>
                    {e.source} ·{' '}
                    {
                      {
                        proactive: '可主动说',
                        asked: '被问到可说',
                        internal: '仅内部参考',
                        handoff: '转人工',
                      }[e.disclosure]
                    }
                  </small>
                </article>
              ))}
            <h2>协作留言</h2>
            {p.comments.map((c) => (
              <p key={c.id}>
                <strong>{c.authorName}</strong>：{c.content}
              </p>
            ))}
          </>
        )}
      </div>
      {p && <PositionCandidates id={p.id} />}
      {p && p.status !== 'closed' && (
        <Decision
          key={`${p.version}-${revision}`}
          pos={p}
          onDone={() => setRevision((n) => n + 1)}
        />
      )}
    </main>
  );
}
