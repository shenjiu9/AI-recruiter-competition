import { useCallback, useRef } from 'react';

export const newIdempotencyKey = (): string =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;

/**
 * 每次打开一个操作生成一个键；重复提交（双击、网络重试）复用同一个键。
 * 操作成功后调用 reset() 让下一次操作拿到新键。
 */
export function useIdempotencyKey(): { key: () => string; reset: () => void } {
  const ref = useRef<string | null>(null);
  const key = useCallback(() => (ref.current ??= newIdempotencyKey()), []);
  const reset = useCallback(() => {
    ref.current = null;
  }, []);
  return { key, reset };
}
