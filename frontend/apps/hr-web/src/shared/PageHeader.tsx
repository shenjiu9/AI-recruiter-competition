import type { ReactNode } from 'react';

export function PageHeader({ title, sub, extra }: { title: ReactNode; sub?: ReactNode; extra?: ReactNode }) {
  return (
    <header style={{ display: 'flex', alignItems: 'flex-end', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
      <div style={{ minWidth: 0 }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 500, lineHeight: 1.35 }}>{title}</h1>
        {sub && <div style={{ marginTop: 4, color: 'var(--rc-ink-2)' }}>{sub}</div>}
      </div>
      {extra && <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>{extra}</div>}
    </header>
  );
}
