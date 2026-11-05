import { Link } from 'react-router-dom';
import { formatDate, type Application } from '@recruiter/domain';
import { StageBadge } from '@recruiter/ui-kit';

/** 投递过的岗位：每条应聘记录一张小卡，进行中在前（PRD 9.3） */
export function ApplicationStrip({ apps, currentId, onSelect }: { apps: Application[]; currentId?: string; onSelect: (id: string) => void }) {
  return (
    <div role="tablist" aria-label="投递过的岗位" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
      {apps.map((a) => {
        const on = a.id === currentId;
        return (
          <div
            key={a.id}
            role="tab"
            tabIndex={0}
            aria-selected={on}
            onClick={() => onSelect(a.id)}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(a.id)}
            style={{
              cursor: 'pointer', padding: '8px 12px', borderRadius: 8, minWidth: 200,
              border: `1px solid ${on ? 'var(--rc-brand)' : 'var(--rc-line)'}`,
              background: on ? 'var(--rc-brand-soft)' : 'var(--rc-surface)',
            }}
          >
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Link to={`/positions/${a.positionId}`} onClick={(e) => e.stopPropagation()} style={{ fontWeight: 500, color: 'var(--rc-ink)' }}>
                {a.positionName}
              </Link>
              <StageBadge stage={a.stage} ended={a.ended?.result} />
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
              {a.ended ? `${formatDate(a.ended.at)} ${a.ended.reason}` : a.subStatus}
            </div>
          </div>
        );
      })}
    </div>
  );
}
