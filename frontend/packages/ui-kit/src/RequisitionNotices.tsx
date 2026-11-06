import { useEffect, useRef, useState } from 'react';
import { ActionButton } from './controls';
import { useApi, toAppError, type ApiClient } from '@recruiter/api-client';

export const TRANSFER_ACTIONS: Record<string, string> = {
  transferred: '审批转交',
  auto_transferred: '组织变更自动转交',
  owner_transferred: '需求负责人交接',
  transfer_blocked: '组织变更待处理',
};

export function RequisitionNotices({
  onOpen,
  revealKey = 0,
}: {
  onOpen: (id: string) => void;
  revealKey?: number;
}) {
  const api = useApi();
  const panel = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (revealKey && panel.current) {
      panel.current.open = true;
      panel.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [revealKey]);
  const [items, setItems] = useState<Awaited<ReturnType<ApiClient['requisitionNotifications']>>>(
    [],
  );
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const refresh = () =>
      void api.requisitionNotifications().then(
        (data) => {
          if (active) {
            setItems(data);
            setError('');
          }
        },
        (e: unknown) => {
          if (active) setError(toAppError(e).message);
        },
      );
    refresh();
    const timer = setInterval(refresh, 30_000);
    window.addEventListener('focus', refresh);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener('focus', refresh);
    };
  }, [api]);
  // 没有消息时不占位置：每个页面顶部都挂着“（0）”只会分散注意力
  if (!items.length && !error && !revealKey) return null;
  return (
    <details ref={panel} id="requisition-notices" className="rc-notices">
      <summary>
        {!!items.length && <span className="dot" aria-hidden />}
        审批与交接消息（{items.length}）
      </summary>
      <div className="body">
        {!items.length && !error && <p>暂无消息</p>}
        {error && <p role="alert">消息加载失败：{error}。稍后会自动重试。</p>}
        {!!items.length && <p style={{ margin: '4px 0 0' }}>显示最近 100 条消息。</p>}
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <ActionButton type="button" onClick={() => onOpen(item.requisition_id)}>
                {TRANSFER_ACTIONS[item.action] ?? item.action} · {item.title}
              </ActionButton>
              <time dateTime={item.at}>{timeFormat.format(new Date(item.at))}</time>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

const timeFormat = new Intl.DateTimeFormat('zh-CN', {
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});
