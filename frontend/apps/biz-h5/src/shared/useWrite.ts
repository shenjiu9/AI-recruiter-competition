import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { Toast } from 'antd-mobile';
import { toAppError, useIdempotencyKey, type WriteOpts } from '@recruiter/api-client';

export function useWrite<V, R>(
  fn: (vars: V, opts: WriteOpts) => Promise<R>,
  cfg: { invalidate?: QueryKey[]; success?: string } = {},
) {
  const qc = useQueryClient();
  const idem = useIdempotencyKey();
  return useMutation({
    mutationFn: (vars: V) => fn(vars, { idempotencyKey: idem.key() }),
    onSuccess: () => {
      idem.reset();
      cfg.invalidate?.forEach((k) => void qc.invalidateQueries({ queryKey: k }));
      if (cfg.success) Toast.show({ icon: 'success', content: cfg.success });
    },
    onError: (e) => {
      const error = toAppError(e);
      if (error.status >= 400 && error.status < 500) idem.reset();
      cfg.invalidate?.forEach((k) => void qc.invalidateQueries({ queryKey: k }));
      Toast.show({ icon: 'fail', content: error.message });
    },
  });
}
