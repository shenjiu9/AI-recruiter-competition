import type { ReactNode } from 'react';

export function PageHeader({ title, sub, extra }: { title: ReactNode; sub?: ReactNode; extra?: ReactNode }) {
  return (
    <header className="hr-page-header">
      <div style={{ minWidth: 0 }}>
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {extra && <div className="extra">{extra}</div>}
    </header>
  );
}
