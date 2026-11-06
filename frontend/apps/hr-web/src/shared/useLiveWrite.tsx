import { useRef, useState } from 'react';
import { Alert, Button } from 'antd';
import { newIdempotencyKey, toAppError, type WriteOpts } from '@recruiter/api-client';

export function useLiveWrite<T, R>(
  operation: (body: T, opts: WriteOpts) => Promise<R>,
  success: (result: R) => void,
  refresh?: () => Promise<unknown>,
) {
  const pending = useRef<{ body: T; key: string }>();
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState('');
  const submit = async (body: T) => {
    if (inFlight.current || conflict) return;
    pending.current ??= { body, key: newIdempotencyKey() };
    inFlight.current = true;
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
      // Business conflicts (cooldown etc.) permit correcting the form.
      const stale = ['VERSION_CONFLICT', 'PERMISSION_CHANGED'].includes(err.code);
      setConflict(stale);
      if (!uncertain) pending.current = undefined;
      setError(err.message + (stale ? '。输入已保留，请关闭后刷新并核对。' : ''));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  return {
    busy,
    locked: busy || retry || conflict,
    submit,
    feedback: (
      <>
        {error && <Alert role="alert" type="error" message={error} />}
        {retry && (
          <Button onClick={() => pending.current && void submit(pending.current.body)}>
            重试本次操作
          </Button>
        )}
        {conflict && (
          <Button
            onClick={async () => {
              if (!refresh) {
                window.location.reload();
                return;
              }
              await refresh();
              setConflict(false);
              setError('数据已刷新，请核对后重新提交，输入已保留。');
            }}
          >
            刷新当前数据
          </Button>
        )}
      </>
    ),
  };
}
