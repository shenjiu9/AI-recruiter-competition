import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { App } from 'antd';
import { isConflict, toAppError, useIdempotencyKey, type WriteOpts } from '@recruiter/api-client';

/**
 * 写操作的统一封装：自动带幂等键（重复提交复用同一个键）、成功后失效相关查询、
 * 版本冲突与其他错误按“发生了什么 + 怎么办”提示。
 */
export function useWrite<V, R>(
  fn: (vars: V, opts: WriteOpts) => Promise<R>,
  cfg: { invalidate?: QueryKey[]; success?: string | ((r: R) => string) } = {},
) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const idem = useIdempotencyKey();
  return useMutation({
    mutationFn: (vars: V) => fn(vars, { idempotencyKey: idem.key() }),
    onSuccess: (r) => {
      idem.reset();
      cfg.invalidate?.forEach((k) => void qc.invalidateQueries({ queryKey: k }));
      if (cfg.success)
        message.success(typeof cfg.success === 'function' ? cfg.success(r) : cfg.success);
    },
    onError: (e) => {
      const err = toAppError(e);
      if (err.status >= 400 && err.status < 500) idem.reset();
      if (isConflict(err)) {
        message.warning(`${err.message}。已为你刷新到最新内容，请确认后再操作。`);
        cfg.invalidate?.forEach((k) => void qc.invalidateQueries({ queryKey: k }));
      } else {
        message.error(err.message);
      }
    },
  });
}
