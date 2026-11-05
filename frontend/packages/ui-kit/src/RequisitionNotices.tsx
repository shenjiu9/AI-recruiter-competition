import { useEffect, useState } from 'react';
import { useApi, toAppError, type ApiClient } from '@recruiter/api-client';

export const TRANSFER_ACTIONS: Record<string, string> = {
  transferred: '审批转交',
  auto_transferred: '组织变更自动转交',
  owner_transferred: '需求负责人交接',
  transfer_blocked: '组织变更待处理',
};

export function RequisitionNotices({ onOpen }: { onOpen: (id: string) => void }) {
  const api = useApi();
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
  return (
    <details style={{ marginBottom: 16, padding: 12 }}>
      <summary>审批与交接消息（{items.length}）</summary>
      {error && <p role="alert">消息加载失败：{error}</p>}
      {!items.length && !error && <p>暂无消息</p>}
      {!!items.length && <p>显示最近 100 条消息。</p>}
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <button type="button" onClick={() => onOpen(item.requisition_id)}>
              {TRANSFER_ACTIONS[item.action] ?? item.action} · {item.title}
            </button>{' '}
            · {new Date(item.at).toLocaleString()}
          </li>
        ))}
      </ul>
    </details>
  );
}
