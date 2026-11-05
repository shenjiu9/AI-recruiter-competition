import { App, Empty } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { DecisionCard as Card } from '@recruiter/domain';
import { usePermission } from '@recruiter/permissions';
import { track } from '@recruiter/telemetry';
import { DecisionCard, EmptyState, QueueRow, type DecisionCardHandle } from '@recruiter/ui-kit';
import { useResolveCard } from '../api';

const isTyping = (el: EventTarget | null) => el instanceof HTMLElement && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));

/**
 * 分诊队列：左侧按剩余时限排序的待决定事项，右侧展开当前项。
 * 键盘：J / K 切换，Enter 采纳建议，D 否决，1–3 展开证据；处理完自动跳到下一项。
 */
export function DecisionQueue({ cards }: { cards: Card[] }) {
  const [local, setLocal] = useState<Record<string, Card>>({});
  const list = useMemo(() => cards.map((c) => local[c.id] ?? c), [cards, local]);
  const [currentId, setCurrentId] = useState<string | undefined>(list[0]?.id);
  const current = list.find((c) => c.id === currentId) ?? list[0];
  const cardRef = useRef<DecisionCardHandle>(null);
  const resolve = useResolveCard();
  const canResolve = usePermission('card.resolve');
  const { message } = App.useApp();

  const move = useCallback(
    (delta: number) => {
      if (!list.length) return;
      const i = Math.max(0, list.findIndex((c) => c.id === current?.id));
      const next = list[Math.min(list.length - 1, Math.max(0, i + delta))];
      if (next) setCurrentId(next.id);
    },
    [list, current],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey || document.querySelector('.ant-modal-wrap')) return;
      const k = e.key.toLowerCase();
      if (k === 'j') move(1);
      else if (k === 'k') move(-1);
      else if (k === 'enter' && canResolve) cardRef.current?.confirmPrimary();
      else if (k === 'd' && canResolve) cardRef.current?.openReject();
      else if (['1', '2', '3'].includes(k)) cardRef.current?.toggleEvidence(Number(k) - 1);
      else return;
      e.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [move, canResolve]);

  if (!list.length)
    return <EmptyState title="没有需要你决定的事" why="AI 正在处理岗位上的沟通和评估，有需要你判断的事项会出现在这里。" action={<Link to="/positions">看看岗位进展</Link>} />;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 340px) minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
      <nav aria-label="待决策队列" className="panel" style={{ overflow: 'hidden' }}>
        {list.map((c) => (
          <QueueRow key={c.id} card={c} current={c.id === current?.id} onSelect={() => setCurrentId(c.id)} />
        ))}
      </nav>
      {current ? (
        <DecisionCard
          key={current.id}
          ref={cardRef}
          card={current}
          showKeyboardHints
          extra={current.candidateId ? <Link to={`/candidates/${current.candidateId}`}>看候选人详情</Link> : null}
          onResolve={async (opt, extras) => {
            const updated = await resolve.mutateAsync({ id: current.id, body: { option: opt.key, expectedVersion: current.version, rejectReason: extras.rejectReason, selected: extras.selected } });
            track('wb_card_action', { card_type: current.type, action: opt.key, accepted_suggestion: !!opt.primary, confidence_level: current.confidence });
            setLocal((m) => ({ ...m, [current.id]: updated }));
            message.success({ content: `已处理：${updated.resolvedNote}` });
            const next = list.find((c) => c.id !== current.id && (local[c.id] ?? c).state === 'open');
            if (next) setTimeout(() => setCurrentId(next.id), 900);
          }}
        />
      ) : (
        <Empty />
      )}
    </div>
  );
}
