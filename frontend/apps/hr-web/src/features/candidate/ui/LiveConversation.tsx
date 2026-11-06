import { useState } from 'react';
import { Alert, Button, Input, Space, Tag } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  useApi,
  toAppError,
  type ConversationCommand,
  type ConversationResult,
  type LiveApplication,
} from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';
import { useAuthenticatedStream } from '@recruiter/realtime';
import { useLiveWrite } from '../../../shared/useLiveWrite';

export function LiveConversation({
  id,
  applications,
}: {
  id: string;
  applications: LiveApplication[];
}) {
  const api = useApi();
  const cache = useQueryClient();
  const session = useSession();
  const [content, setContent] = useState('');
  const [application, setApplication] = useState('');
  const [resolution, setResolution] = useState('');
  const [handoff, setHandoff] = useState('');
  const [link, setLink] = useState<ConversationResult>();
  const key = ['live-conversation', id];
  const query = useQuery({ queryKey: key, queryFn: () => api.liveConversation(id) });
  useAuthenticatedStream(
    `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1/hr/stream?candidate_id=${encodeURIComponent(id)}`,
    session?.token,
    () => {
      void query.refetch();
      void cache.invalidateQueries({ queryKey: ['live-candidate', id] });
    },
  );
  const op = useLiveWrite<ConversationCommand, ConversationResult>(
    (body, opts) => api.conversationCommand(id, body, opts),
    (result) => {
      cache.setQueryData(key, result.conversation);
      if (result.url) setLink(result);
      else setLink(undefined);
      setContent('');
      void cache.invalidateQueries({ queryKey: ['live-candidate', id] });
    },
    () => query.refetch(),
  );
  const c = query.data;
  if (query.isError) return <Alert type="error" message={toAppError(query.error).message} />;
  if (!c) return <p>正在加载会话…</p>;
  const run = (action: ConversationCommand['action']) =>
    void op.submit({
      action,
      expected_version: c.version,
      content: action === 'take_over' || action === 'hand_back' ? handoff : undefined,
    });
  const otherOwner = !!c.owner_id && c.owner_id !== session?.userId;
  const canReassign =
    otherOwner && !!session?.roles.includes('recruiting_lead') && !!handoff.trim();
  const latest = [...c.messages].reverse().find((m) => m.sender === 'candidate');
  return (
    <section className="panel" style={{ padding: 20, marginTop: 20 }} aria-label="候选人沟通">
      <h2>候选人沟通</h2>
      <Tag>
        会话授权：
        {c.consent === 'granted' ? '已授权' : c.consent === 'revoked' ? '已撤回授权' : '尚未授权'}
      </Tag>
      <p>
        {c.mode === 'hr' ? `人工接管中 · ${c.owner_id}` : '待 HR 处理'}。当前未启用 AI 自动回复。
      </p>
      {otherOwner && session?.roles.includes('recruiting_lead') && (
        <Input
          aria-label="会话交接说明"
          placeholder="接管人离职或需调整时，请填写交接说明"
          value={handoff}
          onChange={(e) => setHandoff(e.target.value)}
          disabled={op.locked}
        />
      )}
      <Space wrap>
        <Button disabled={op.locked} onClick={() => run('issue_link')}>
          生成专属链接
        </Button>
        <Button disabled={op.locked} onClick={() => run('revoke_links')}>
          撤销已有链接
        </Button>
        <Button
          disabled={op.locked || (c.mode === 'hr' && !canReassign)}
          onClick={() => run('take_over')}
        >
          接管会话
        </Button>
        <Button
          disabled={op.locked || (c.owner_id !== session?.userId && !canReassign)}
          onClick={() => run('hand_back')}
        >
          交还会话
        </Button>
      </Space>
      {link?.url && (
        <div>
          <p>
            链接有效期至 {new Date(link.expires_at!).toLocaleString()}
            。新链接会使旧链接失效，请核对身份后分享。
          </p>
          <Input aria-label="候选人专属链接" value={link.url} readOnly />
          <a href={link.url} target="_blank" rel="noreferrer">
            打开候选人页面
          </a>
        </div>
      )}
      {(c.do_not_contact || c.consent === 'revoked') && (
        <Alert type="warning" message="候选人已停止联系或撤回授权，待发送消息已取消。" />
      )}
      <div
        role="log"
        aria-label="聊天记录"
        style={{ maxHeight: 380, overflowY: 'auto', marginBlock: 16 }}
      >
        {c.messages.length === 0 && <p>暂无消息。候选人可在专属页面发送消息。</p>}
        {c.messages.map((m) => (
          <article key={m.id} style={{ padding: 12, borderBottom: '1px solid #eee' }}>
            <strong>
              {m.sender === 'candidate' ? '候选人' : m.sender === 'ai' ? 'AI 招聘助手' : 'HR'}
            </strong>{' '}
            · H5 · {new Date(m.created_at).toLocaleString()}
            <Tag>
              {m.status === 'queued'
                ? `等待发送 ${new Date(m.due_at!).toLocaleString()}`
                : m.status === 'cancelled'
                  ? '已取消'
                  : '已送达页面'}
            </Tag>
            <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{m.content}</p>
            <small>
              {m.application_ids
                .map((aid) => applications.find((a) => a.id === aid)?.position_name ?? '关联应聘')
                .join('、') || '通用沟通'}{' '}
              {m.reason}
            </small>
          </article>
        ))}
      </div>
      <label>
        关联岗位{' '}
        <select
          aria-label="消息关联岗位"
          value={application}
          onChange={(e) => setApplication(e.target.value)}
          disabled={op.locked}
        >
          <option value="">通用沟通（须有全部岗位权限）</option>
          {applications
            .filter((a) => !a.restricted && a.can_edit)
            .map((a) => (
              <option key={a.id} value={a.id}>
                {a.position_name}
              </option>
            ))}
        </select>
      </label>
      <Input.TextArea
        aria-label="HR 消息"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        maxLength={4000}
        disabled={op.locked}
      />
      <p>
        主动消息在北京时间 9–21 点发送；最近 30 分钟消息的回复可在 7–23
        点发送。其余时段进入发送队列。
      </p>
      <Button
        type="primary"
        disabled={
          op.locked ||
          !content.trim() ||
          c.owner_id !== session?.userId ||
          c.do_not_contact ||
          c.consent === 'revoked'
        }
        onClick={() =>
          void op.submit({
            action: 'send',
            expected_version: c.version,
            content,
            application_ids: application ? [application] : [],
            reply_to_id: latest?.id,
          })
        }
      >
        发送消息
      </Button>
      {op.feedback}
      {c.requests.length > 0 && (
        <>
          <h3>候选人资料请求</h3>
          <Input
            aria-label="资料处理结果"
            placeholder="核实并编辑资料后，在此记录实际处理结果"
            value={resolution}
            onChange={(e) => setResolution(e.target.value)}
            disabled={op.locked}
          />
          {c.requests.map((r) => (
            <p key={r.id}>
              {r.kind === 'deletion_request' ? '删除资料' : '更正资料'}：{r.content} · 请于{' '}
              {new Date(r.due_at).toLocaleDateString()} 前核实处理；使用上方资料编辑或删除操作。
              {r.status === 'resolved'
                ? `已处理：${r.resolution}`
                : r.kind === 'correction_request' && (
                    <Button
                      disabled={op.locked || !resolution.trim()}
                      onClick={() =>
                        void op.submit({
                          action: 'resolve_request',
                          expected_version: c.version,
                          request_id: r.id,
                          content: resolution,
                        })
                      }
                    >
                      登记处理结果
                    </Button>
                  )}
            </p>
          ))}
        </>
      )}
    </section>
  );
}
