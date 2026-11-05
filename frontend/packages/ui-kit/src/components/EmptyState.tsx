import type { ReactNode } from 'react';

/** 空状态：这里是什么 + 为什么是空的 + 下一步做什么 */
export function EmptyState({ title, why, action }: { title: string; why: string; action?: ReactNode }) {
  return (
    <div className="rc-empty">
      <h3>{title}</h3>
      <p>{why}</p>
      {action}
    </div>
  );
}
