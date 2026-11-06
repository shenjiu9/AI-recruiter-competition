import type { WorkbenchSummary } from '@recruiter/domain';

/** AI 简报：用一句话代替 4 张数字卡，数字可点击定位（PRD 6.1、AI 简报） */
export function BriefLine({ s, onGo }: { s: WorkbenchSummary; onGo: (tab: 'cards' | 'handoffs' | 'activity') => void }) {
  return (
    <p className="rc-brief">
      {s.userName}，今天有{' '}
      <button type="button" className="go num" onClick={() => onGo('cards')}>
        {s.pendingDecisions} 件事
      </button>{' '}
      等你决定，其中 <span className="num">{s.dueToday}</span> 件今天到期；
      <button type="button" className="go num" onClick={() => onGo('handoffs')}>
        {s.handoffs} 个会话
      </button>{' '}
      转给了你；AI 今天完成了{' '}
      <button type="button" className="go num" onClick={() => onGo('activity')}>
        {s.aiActionsToday} 个动作
      </button>
      ；本周录用 <span className="num">{s.hiredThisWeek}</span> 人。
    </p>
  );
}
