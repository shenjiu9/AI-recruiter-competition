import {
  ArrowUpOutlined,
  BarChartOutlined,
  CalendarOutlined,
  CheckSquareOutlined,
  DeleteOutlined,
  FileTextOutlined,
  FundOutlined,
  RobotOutlined,
  SearchOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useSession } from '@recruiter/auth';
import './assistant.css';
import { Block } from './Blocks';
import { JobCard } from './JobCard';
import { useAssistant, type Turn } from './state';

export const STARTERS: { icon: ReactNode; title: string; text: string }[] = [
  { icon: <CheckSquareOutlined />, title: '今天要处理什么', text: '今天有什么要处理' },
  { icon: <BarChartOutlined />, title: '岗位招聘进度', text: '岗位招聘进度' },
  { icon: <CalendarOutlined />, title: '最近的面试', text: '最近的面试安排' },
  { icon: <RobotOutlined />, title: '待复核的 AI 结果', text: '待我复核的 AI 结果' },
  { icon: <FundOutlined />, title: '招聘漏斗与数据', text: '看看招聘漏斗' },
  { icon: <SearchOutlined />, title: '在人才库找人', text: '找会 Excel 的候选人' },
  { icon: <FileTextOutlined />, title: '让 AI 写 JD', text: '帮客服专员写一版 JD' },
  { icon: <TeamOutlined />, title: '决策卡与提醒', text: '有哪些决策卡要处理' },
];

function Bubble({ turn }: { turn: Turn }) {
  const { retry, send, busy, turns } = useAssistant();
  if (turn.role === 'user')
    return (
      <div className="as-msg as-msg-user">
        <div className="as-bubble">{turn.text}</div>
      </div>
    );
  const last = turns[turns.length - 1]?.id === turn.id;
  return (
    <div className={`as-msg as-msg-ai${turn.tone ? ' as-msg-' + turn.tone : ''}`}>
      <span className="as-msg-avatar" aria-hidden>
        <RobotOutlined />
      </span>
      <div className="as-msg-body">
        {turn.pending ? (
          <div className="as-typing" role="status" aria-label="AI 正在思考">
            <span />
            <span />
            <span />
          </div>
        ) : turn.error ? (
          <div className="as-bubble as-bubble-error" role="alert">
            {turn.error}
            <Button size="small" type="link" onClick={() => retry(turn.id)} disabled={busy}>
              重新发送
            </Button>
          </div>
        ) : (
          <>
            {turn.text && <div className="as-text">{turn.text}</div>}
            {turn.reply?.blocks.map((b, i) => (
              <Block key={i} block={b} />
            ))}
            {turn.job && <JobCard initial={turn.job} />}
            {last && !!turn.reply?.suggestions.length && (
              <div className="as-suggest" aria-label="接下来可以问">
                {turn.reply.suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="as-suggest-chip"
                    onClick={() => send(s)}
                    disabled={busy}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** 输入框：Enter 发送，Shift+Enter 换行，输入法组字时不发送 */
export function Composer({
  autoFocus,
  placeholder,
}: {
  autoFocus?: boolean;
  placeholder?: string;
}) {
  const { send, busy, focus } = useAssistant();
  const [text, setText] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, [text]);
  const submit = () => {
    if (!text.trim() || busy) return;
    send(text);
    setText('');
  };
  const context = [focus.candidate_name, focus.position_name].filter(Boolean).join(' · ');
  return (
    <form
      className="as-composer"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      {context && (
        <div className="as-context" title="说“他”“这个岗位”时指的就是这里">
          <UserOutlined aria-hidden /> 正在聊：{context}
        </div>
      )}
      <div className="as-composer-box">
        <textarea
          ref={ref}
          rows={1}
          aria-label="和 AI 招聘助手对话"
          placeholder={placeholder ?? '问进展、让 AI 写东西，或者让我推进流程…'}
          value={text}
          maxLength={4000}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <Button
          htmlType="submit"
          type="primary"
          shape="circle"
          icon={<ArrowUpOutlined />}
          aria-label="发送"
          disabled={!text.trim() || busy}
        />
      </div>
      <div className="as-hint">
        推进、淘汰、发消息会先给你确认；打标签这类小操作直接执行，可撤销 · Enter 发送
      </div>
    </form>
  );
}

export function Conversation({ compact = false }: { compact?: boolean }) {
  const { turns, send, busy, clear } = useAssistant();
  const session = useSession();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [turns]);
  return (
    <div className={`as-conversation${compact ? ' as-compact' : ''}`}>
      <div className="as-log" role="log" aria-live="polite" aria-label="对话记录">
        {turns.length === 0 ? (
          <div className="as-empty">
            <div className="as-empty-icon" aria-hidden>
              <RobotOutlined />
            </div>
            <h2>{session?.name ? `${session.name}，` : ''}今天想先处理什么？</h2>
            <p>
              你在系统里能看到的信息都可以直接问我，进度和数据会用图表回答。我也能让 AI 写
              JD、做评估，
              帮你推进候选人、发消息。打标签、设重点这类小操作我直接做，可以撤销；推进、淘汰、发消息会先请你确认。
            </p>
            <div className="as-starters">
              {STARTERS.map((s) => (
                <button
                  key={s.text}
                  type="button"
                  className="as-starter"
                  onClick={() => send(s.text)}
                  disabled={busy}
                >
                  <span className="as-starter-icon" aria-hidden>
                    {s.icon}
                  </span>
                  <span>
                    <strong>{s.title}</strong>
                    <span>“{s.text}”</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((t) => <Bubble key={t.id} turn={t} />)
        )}
        <div ref={end} />
      </div>
      {turns.length > 0 && (
        <div className="as-toolbar">
          <Tooltip title="清空对话（不影响任何业务数据）">
            <Button
              size="small"
              type="text"
              icon={<DeleteOutlined />}
              onClick={clear}
              disabled={busy}
            >
              新对话
            </Button>
          </Tooltip>
        </div>
      )}
      <Composer autoFocus={!compact} />
    </div>
  );
}
