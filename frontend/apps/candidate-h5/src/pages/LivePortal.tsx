import { useRef, useState } from 'react';
import { Button, Dialog, NavBar, NoticeBar } from 'antd-mobile';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  useApi,
  newIdempotencyKey,
  toAppError,
  type ConversationCommand,
} from '@recruiter/api-client';
import { useAuthenticatedStream } from '@recruiter/realtime';

export function LivePortal() {
  const [token] = useState(() => new URLSearchParams(location.hash.slice(1)).get('t') ?? '');
  const api = useApi();
  const cache = useQueryClient();
  const [content, setContent] = useState('');
  const [note, setNote] = useState('');
  const [application, setApplication] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(false);
  const [stale, setStale] = useState(false);
  const pending = useRef<{ body: ConversationCommand; key: string }>();
  const inFlight = useRef(false);
  const key = ['candidate-self-service'];
  const query = useQuery({
    queryKey: key,
    queryFn: () => api.livePortal(token),
    enabled: !!token,
    retry: false,
  });
  useAuthenticatedStream(
    `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1/candidate/stream`,
    token,
    () => {
      void query.refetch();
    },
  );
  const c = query.data;
  async function submit(body: ConversationCommand) {
    if (inFlight.current || stale) return;
    pending.current ??= { body, key: newIdempotencyKey() };
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await api.livePortalCommand(token, pending.current.body, {
        idempotencyKey: pending.current.key,
      });
      cache.setQueryData(key, result);
      pending.current = undefined;
      setRetry(false);
      if (body.action === 'send') setContent('');
      if (body.action.endsWith('_request')) setNote('');
    } catch (e) {
      const err = toAppError(e);
      setError(err.message);
      const uncertain = err.status === 0 || err.status >= 500;
      setRetry(uncertain);
      setStale(err.code === 'VERSION_CONFLICT');
      if (!uncertain) pending.current = undefined;
      if (err.status === 401) void query.refetch();
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  if (!token || query.isError)
    return (
      <main style={{ padding: 24 }}>
        <h1>专属链接不可用</h1>
        <p>
          {query.isError
            ? toAppError(query.error).message
            : '请使用招聘 HR 提供的专属链接打开此页面。'}
        </p>
        <Button onClick={() => void query.refetch()}>重新加载</Button>
      </main>
    );
  if (!c) return <p style={{ padding: 24 }}>正在加载您的应聘信息…</p>;
  const locked = busy || retry || stale;
  const run = (action: ConversationCommand['action'], text?: string) =>
    void submit({ action, expected_version: c.version, content: text });
  const confirm = (action: ConversationCommand['action'], message: string) =>
    void Dialog.confirm({ content: message, onConfirm: () => run(action) });
  return (
    <main style={{ maxWidth: 680, margin: 'auto', padding: 16, paddingBottom: 80 }}>
      <NavBar back={null}>招聘沟通与个人资料</NavBar>
      <h1 style={{ fontSize: 22 }}>{c.profile?.name}，您好</h1>
      <NoticeBar
        content={
          c.mode === 'hr'
            ? '招聘 HR 已接管会话，消息由人工回复。'
            : '您的消息会提交招聘 HR 处理，当前未启用 AI 自动回复。'
        }
      />
      <section className="rm-card">
        <h2>个人信息授权</h2>
        <p>
          为处理您的应聘，我们保存您提供的简历、联系方式和沟通记录，并在您同意后用于招聘匹配及 AI
          辅助评估。招聘决定由人工作出。资料保留至 {c.retention_until}
          ，您可随时撤回授权、申请更正或删除。问题可在下方联系招聘 HR。
        </p>
        <p>
          授权状态：
          {c.consent === 'granted' ? '已授权' : c.consent === 'revoked' ? '已撤回' : '尚未授权'}
          。未授权也可以发送消息。
        </p>
        {c.consent !== 'granted' ? (
          <Button
            disabled={locked || c.do_not_contact}
            onClick={() =>
              confirm('consent', '您同意以上个人信息处理用途，包括招聘匹配和 AI 辅助评估吗？')
            }
          >
            同意并授权
          </Button>
        ) : (
          <Button
            disabled={locked}
            onClick={() =>
              confirm(
                'revoke',
                '撤回后停止 AI 评估及后续主动联系，待发送消息将取消。已保存资料可另行申请删除。',
              )
            }
          >
            撤回授权
          </Button>
        )}
        <Button
          disabled={locked || c.do_not_contact}
          onClick={() =>
            confirm('do_not_contact', '确认要求招聘团队不再联系您？待发送消息将取消。')
          }
        >
          {c.do_not_contact ? '已要求不再联系' : '不再联系我'}
        </Button>
      </section>
      <section className="rm-card">
        <h2>我的应聘</h2>
        {c.applications?.length ? (
          c.applications.map((a) => (
            <p key={a.id}>
              {a.position_name} · {a.status}
            </p>
          ))
        ) : (
          <p>暂未关联岗位，您可以先与 HR 沟通。</p>
        )}
      </section>
      <section className="rm-card">
        <h2>与招聘 HR 沟通</h2>
        <Button disabled={locked} onClick={() => run('ask_human')}>
          请求人工处理
        </Button>
        <div role="log" aria-label="聊天记录">
          {c.messages.map((m) => (
            <article
              key={m.id}
              style={{
                padding: 12,
                background: m.sender === 'candidate' ? '#edf5ff' : '#f5f5f5',
                marginBlock: 10,
                borderRadius: 8,
              }}
            >
              <strong>{m.sender === 'candidate' ? '我' : '招聘 HR'}</strong> ·{' '}
              {new Date(m.created_at).toLocaleString()}
              <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{m.content}</p>
              <small>
                {m.application_ids
                  .map((aid) => c.applications?.find((a) => a.id === aid)?.position_name ?? '')
                  .join('、')}
              </small>
            </article>
          ))}
        </div>
        <label>
          关联应聘{' '}
          <select
            aria-label="关联应聘"
            value={application}
            onChange={(e) => setApplication(e.target.value)}
            disabled={locked}
          >
            <option value="">通用沟通</option>
            {c.applications?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.position_name}
              </option>
            ))}
          </select>
        </label>
        <textarea
          style={{ width: '100%', boxSizing: 'border-box', padding: 12, fontSize: 16 }}
          rows={3}
          aria-label="候选人消息"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          maxLength={4000}
          disabled={locked}
          placeholder="填写想向招聘 HR 了解的内容"
        />
        <Button
          color="primary"
          disabled={locked || !content.trim()}
          onClick={() =>
            void submit({
              action: 'send',
              expected_version: c.version,
              content,
              application_ids: application ? [application] : [],
            })
          }
        >
          发送消息
        </Button>
      </section>
      {error && <p role="alert">{error}</p>}
      {retry && (
        <Button
          disabled={busy}
          onClick={() => pending.current && void submit(pending.current.body)}
        >
          重试本次操作
        </Button>
      )}
      {stale && (
        <Button
          onClick={async () => {
            await query.refetch();
            setStale(false);
            setError('请核对最新记录后重新提交，输入已保留。');
          }}
        >
          刷新最新记录
        </Button>
      )}
      <section className="rm-card">
        <h2>查看和管理我的资料</h2>
        <details>
          <summary>查看已保存资料</summary>
          {Object.entries(c.profile ?? {})
            .filter(([, v]) => v !== '' && v != null)
            .map(([k, v]) => (
              <p key={k}>
                {PROFILE_LABELS[k] ?? k}：{v}
              </p>
            ))}
        </details>
        <textarea
          style={{ width: '100%', boxSizing: 'border-box', padding: 12, fontSize: 16 }}
          rows={3}
          aria-label="资料请求说明"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={4000}
          disabled={locked}
          placeholder="请说明需要更正的资料或删除请求，HR 将核实并在 15 天内处理。"
        />
        <Button disabled={locked || !note.trim()} onClick={() => run('correction_request', note)}>
          提交更正请求
        </Button>
        <Button
          disabled={locked || !note.trim()}
          onClick={() =>
            void Dialog.confirm({
              content:
                '确认提交资料删除请求？HR 将核实身份并在 15 天内处理；提交请求不会立即删除资料。',
              onConfirm: () => run('deletion_request', note),
            })
          }
        >
          申请删除资料
        </Button>
        {c.requests.map((r) => (
          <p key={r.id}>
            {r.kind === 'deletion_request' ? '删除请求' : '更正请求'}
            {r.status === 'resolved' ? `已处理：${r.resolution}` : '已提交'}：{r.content} · 处理期限{' '}
            {new Date(r.due_at).toLocaleDateString()}
          </p>
        ))}
      </section>
    </main>
  );
}
const PROFILE_LABELS: Record<string, string> = {
  name: '姓名',
  phone: '手机号',
  email: '邮箱',
  city: '城市',
  company: '当前公司',
  title: '当前职位',
  school: '学校',
  degree: '学历',
  graduation_year: '毕业年份',
  years_exp: '工作年限',
  skills: '技能',
  experience: '工作经历',
  education: '教育经历',
  certificates: '证书',
  expected_city: '期望城市',
  expected_salary: '期望薪资',
};
