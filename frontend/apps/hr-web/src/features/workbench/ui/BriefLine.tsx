import type { WorkbenchSummary } from '@recruiter/domain';

const numStyle = { border: 0, background: 'none', padding: 0, font: 'inherit', color: 'var(--rc-brand)', fontWeight: 500, cursor: 'pointer', textDecoration: 'underline', textDecorationStyle: 'dotted', textUnderlineOffset: 4 } as const;

/** AI 简报：用一句话代替 4 张数字卡，数字可点击定位（PRD 6.1、AI 简报） */
export function BriefLine({ s, onGo }: { s: WorkbenchSummary; onGo: (tab: 'cards' | 'handoffs' | 'activity') => void }) {
  return (
    <p style={{ fontSize: 16, lineHeight: 1.7, margin: '0 0 20px', maxWidth: 880 }}>
      {s.userName}，今天有{' '}
      <button type="button" style={numStyle} onClick={() => onGo('cards')}>
        {s.pendingDecisions} 件事
      </button>{' '}
      等你决定，其中 {s.dueToday} 件今天到期；
      <button type="button" style={numStyle} onClick={() => onGo('handoffs')}>
        {s.handoffs} 个会话
      </button>{' '}
      转给了你；AI 今天完成了{' '}
      <button type="button" style={numStyle} onClick={() => onGo('activity')}>
        {s.aiActionsToday} 个动作
      </button>
      ；本周录用 <span className="num">{s.hiredThisWeek}</span> 人。
    </p>
  );
}
