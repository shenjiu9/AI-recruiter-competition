import { STAGES, stageLabel, type FunnelStage, type Stage } from '@recruiter/domain';

/** 6 阶段漏斗：宽度按到达人数比例；转化率低于 50% 的一段标为瓶颈（PRD 8.2） */
export function FunnelBar({ stages, onPick }: { stages: FunnelStage[]; onPick?: (s: Stage) => void }) {
  const max = Math.max(1, ...stages.map((s) => s.reached));
  return (
    <ol aria-label="招聘阶段漏斗" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
      {STAGES.map((st, i) => {
        const s = stages.find((x) => x.stage === st) ?? { stage: st, reached: 0, current: 0 };
        const prev = i > 0 ? stages.find((x) => x.stage === STAGES[i - 1]) : undefined;
        const rate = prev && prev.reached ? s.reached / prev.reached : undefined;
        const bottleneck = rate !== undefined && rate < 0.2;
        return (
          <li key={st} style={{ display: 'grid', gridTemplateColumns: '112px minmax(0,1fr) 120px', gap: 12, alignItems: 'center' }}>
            <button type="button" onClick={() => onPick?.(st)} style={{ border: 0, background: 'none', padding: 0, textAlign: 'left', cursor: 'pointer', color: 'var(--rc-ink)', font: 'inherit' }}>
              {stageLabel(st)}
            </button>
            <div style={{ height: 20, background: 'var(--rc-surface-2)', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ width: `${(s.reached / max) * 100}%`, minWidth: s.reached ? 2 : 0, height: '100%', background: bottleneck ? 'var(--rc-warn)' : 'var(--rc-brand)', opacity: bottleneck ? 0.85 : 0.75 }} />
            </div>
            <span className="num" style={{ fontSize: 12, color: 'var(--rc-ink-2)', textAlign: 'right' }}>
              {s.reached} 人{rate !== undefined && <span style={{ color: bottleneck ? 'var(--rc-warn)' : 'var(--rc-ink-3)', marginLeft: 8 }}>{Math.round(rate * 100)}%{bottleneck ? ' 瓶颈' : ''}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
