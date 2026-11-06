import { useRef, useState } from 'react';
import { newIdempotencyKey } from './idempotency';
import { toAppError } from './errors';
import type { WriteOpts } from './client';

export function useReliableWrite<T, R>(
  operation: (body: T, opts: WriteOpts) => Promise<R>,
  success: (result: R) => void,
) {
  const pending = useRef<{ body: T; key: string }>();
  const flight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState('');
  async function submit(body: T) {
    if (flight.current || conflict) return;
    pending.current ??= { body: structuredClone(body), key: newIdempotencyKey() };
    flight.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await operation(pending.current.body, { idempotencyKey: pending.current.key });
      pending.current = undefined;
      setRetry(false);
      success(result);
    } catch (e) {
      const err = toAppError(e);
      const uncertain = err.status === 0 || err.status >= 500;
      setRetry(uncertain);
      setConflict(err.code === 'VERSION_CONFLICT');
      setError(err.message);
      if (!uncertain) pending.current = undefined;
    } finally {
      flight.current = false;
      setBusy(false);
    }
  }
  return {
    busy,
    retry,
    conflict,
    error,
    locked: busy || retry || conflict,
    submit,
    retryAction: () => pending.current && void submit(pending.current.body),
    refreshed: () => {
      setConflict(false);
      setError('已刷新，请核对最新安排后重新提交。输入已保留。');
    },
  };
}
