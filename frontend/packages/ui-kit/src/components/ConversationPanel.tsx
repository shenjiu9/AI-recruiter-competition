import { Button, Input, Space } from 'antd';
import { useState } from 'react';
import { formatDateTime, formatDue, type Conversation } from '@recruiter/domain';

const MODE_TEXT = {
  ai: 'AI 自动回复中',
  handoff: '已转人工',
  taken_over: '你已接管，AI 只给草稿，不会发送',
} as const;

export interface ConversationPanelProps {
  conversation: Conversation;
  candidateName: string;
  canTakeOver: boolean;
  onTakeOver: () => Promise<void>;
  onHandBack: () => Promise<void>;
  onSend: (text: string) => Promise<void>;
}

/** 统一会话：AI / HR / 候选人消息与 AI 草稿；接管与交还（PRD 6.3） */
export function ConversationPanel({ conversation, candidateName, canTakeOver, onTakeOver, onHandBack, onSend }: ConversationPanelProps) {
  const draft = conversation.messages.find((m) => m.draft);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const mode = conversation.mode;
  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="会话" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="rc-convbar" data-mode={mode} role="status">
        <strong style={{ fontWeight: 500 }}>{MODE_TEXT[mode]}</strong>
        {mode === 'handoff' && conversation.handoffReason && (
          <span>
            原因：{conversation.handoffReason}
            {conversation.handoffDueAt && `，请在 ${formatDue(conversation.handoffDueAt).text} 前回复`}
          </span>
        )}
        <span style={{ marginLeft: 'auto' }}>
          {mode !== 'taken_over' && canTakeOver && (
            <Button size="small" type={mode === 'handoff' ? 'primary' : 'default'} loading={busy} onClick={() => wrap(onTakeOver)}>
              接管会话
            </Button>
          )}
          {mode === 'taken_over' && (
            <Button size="small" loading={busy} onClick={() => wrap(onHandBack)}>
              交还 AI
            </Button>
          )}
        </span>
      </div>

      <div className="rc-chat">
        {conversation.messages.filter((m) => !m.draft).map((m) => (
          <div key={m.id} className={`rc-msg ${m.sender}`}>
            <div className="who">
              {m.sender === 'ai' && <span className="rc-tag rc-ai">AI</span>}
              <span>{m.sender === 'candidate' ? candidateName : m.sender === 'hr' ? (m.senderName ?? 'HR') : 'AI 招聘助手'}</span>
              <span className="num">{formatDateTime(m.at)}</span>
              {m.kbRefs?.length ? <span title="引用的知识库条目">依据 {m.kbRefs.join('、')}</span> : null}
            </div>
            <div className="rc-bubble">{m.text}</div>
          </div>
        ))}
        {draft && (
          <div className="rc-msg draft">
            <div className="who">
              <span className="rc-tag rc-ai">AI 草稿</span>
              <span>还没发出，需要你确认</span>
            </div>
            <div className="rc-bubble">{draft.text}</div>
          </div>
        )}
      </div>

      {(mode === 'taken_over' || mode === 'handoff') && (
        <div>
          <Input.TextArea
            aria-label={`以 HR 身份回复${candidateName}`}
            autoSize={{ minRows: 2, maxRows: 6 }}
            value={text}
            placeholder={`以 HR 身份回复${candidateName}`}
            onChange={(e) => setText(e.target.value)}
          />
          <Space style={{ marginTop: 8 }}>
            <Button
              type="primary"
              disabled={!text.trim()}
              loading={busy}
              onClick={() =>
                wrap(async () => {
                  await onSend(text.trim());
                  setText('');
                })
              }
            >
              发送
            </Button>
            {draft && <Button onClick={() => setText(draft.text)}>使用 AI 草稿</Button>}
          </Space>
        </div>
      )}
    </section>
  );
}
