// 服务端推送：SSE 订阅；断线自动重连，连续失败退回轮询（实现文档第 8 节）
import { useEffect, useRef } from 'react';

export interface StreamEvent {
  type: string;
  id: string;
  payload: Record<string, unknown>;
}

export interface StreamOptions {
  url?: string;
  /** 无法建立 SSE 时的轮询回调，默认 5 秒一次 */
  onPoll?: () => void;
  pollMs?: number;
}

export function useEventStream(topics: string[], onEvent: (e: StreamEvent) => void, opts: StreamOptions = {}): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;
  const topicKey = topics.join(',');

  useEffect(() => {
    const { url, onPoll, pollMs = 5000 } = opts;
    let es: EventSource | null = null;
    let failures = 0;
    let timer: ReturnType<typeof setInterval> | null = null;
    const startPolling = () => {
      if (!timer && onPoll) timer = setInterval(onPoll, pollMs);
    };
    if (!url || typeof EventSource === 'undefined') {
      startPolling();
    } else {
      es = new EventSource(`${url}?topics=${encodeURIComponent(topicKey)}`, { withCredentials: true });
      es.onmessage = (m) => {
        failures = 0;
        try {
          handler.current(JSON.parse(m.data) as StreamEvent);
        } catch {
          /* 忽略无法解析的事件 */
        }
      };
      es.onerror = () => {
        failures += 1;
        if (failures >= 3) {
          es?.close();
          startPolling();
        }
      };
    }
    return () => {
      es?.close();
      if (timer) clearInterval(timer);
    };
    // opts 的函数引用变化不重建连接
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicKey, opts.url]);
}
