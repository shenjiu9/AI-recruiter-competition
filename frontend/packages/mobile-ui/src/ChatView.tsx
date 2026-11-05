import { useEffect, useRef, type ReactNode } from 'react';
import { formatTime, type Message } from '@recruiter/domain';

/** 候选人端会话：AI 消息带“AI”标记；mine = 候选人自己 */
export function ChatView({ messages, footer }: { messages: Message[]; footer?: ReactNode }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [messages.length]);
  return (
    <div className="rm-chat" role="log" aria-live="polite" aria-label="与招聘助手的对话">
      {messages.map((m) => {
        const mine = m.sender === 'candidate';
        return (
          <div key={m.id} className={`rm-msg ${mine ? 'mine' : m.sender}`}>
            <div className="who">
              {m.sender === 'ai' && <span className="rm-tag-ai">AI</span>}
              <span>{mine ? '我' : m.sender === 'ai' ? '招聘助手' : (m.senderName ?? '招聘顾问')}</span>
              <span>{formatTime(m.at)}</span>
            </div>
            <div className="rm-bubble">{m.text}</div>
          </div>
        );
      })}
      {footer}
      <div ref={end} />
    </div>
  );
}
