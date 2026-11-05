import { cardTypeLabel, formatDue, type DecisionCard } from '@recruiter/domain';
import { ConfidenceTag } from './Tags';

/** 工作台分诊队列中的一行：按剩余时限排序，当前项左侧藏青标记 */
export function QueueRow({ card, current, onSelect }: { card: DecisionCard; current: boolean; onSelect: () => void }) {
  const due = formatDue(card.dueAt);
  return (
    <button type="button" className="rc-qrow" aria-current={current} data-state={card.state} onClick={onSelect}>
      <span className="title">{card.title}</span>
      <span className="due" data-urgent={due.urgent && card.state === 'open'}>
        {card.state === 'done' ? '已处理' : card.state === 'void' ? '已失效' : due.text}
      </span>
      <span className="sub">
        <span>{cardTypeLabel(card.type)}</span>
        <span>{card.positionName}</span>
        {card.isKey && <span style={{ color: 'var(--rc-brand)' }}>关键候选人</span>}
      </span>
      <span>
        <ConfidenceTag value={card.confidence} showValue={false} />
      </span>
    </button>
  );
}
