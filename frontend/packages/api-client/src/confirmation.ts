import { useEffect, useRef, useState } from 'react';
import type { ConfirmationPreview, RequisitionDetail } from './client';
import { useApi } from './context';
import { toAppError } from './errors';
import { newIdempotencyKey } from './idempotency';

export const CONFIRMATION_FIELDS: { key: string; label: string; options?: string[] }[] = [
  { key: 'title', label: '职位名称' },
  { key: 'recruitType', label: '招聘类型', options: ['社招', '校招', '活水'] },
  { key: 'employmentType', label: '用工类型', options: ['正式', '外包', '实习'] },
  { key: 'reqType', label: '需求类型', options: ['新增', '替补', '追加'] },
  { key: 'headcount', label: '招聘人数' },
  { key: 'hcRequest', label: '申请增编人数' },
  { key: 'series', label: '职位序列' },
  { key: 'level', label: '职级范围' },
  { key: 'city', label: '工作地点' },
  { key: 'reportTo', label: '汇报对象' },
  { key: 'expectedOnboard', label: '期望到岗' },
  { key: 'salary', label: '薪资带宽' },
  { key: 'reason', label: '招聘原因' },
  { key: 'duties', label: '岗位职责' },
  { key: 'requirements', label: '任职资格' },
];
export const confirmationFieldLabel = (key: string) =>
  key === 'reportToId'
    ? '汇报对象账号'
    : (CONFIRMATION_FIELDS.find((field) => field.key === key)?.label ?? key);

/** Pin the original version while editing; a refresh must never silently rebase edits. */
export function useConfirmation(initial: RequisitionDetail, onSuccess: () => void) {
  const api = useApi();
  const [base] = useState(initial);
  const [fields, setFields] = useState(initial.fields);
  const [result, setResult] = useState<{ body: string; value: ConfirmationPreview }>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  const [conflict, setConflict] = useState(false);
  const key = useRef<string>();
  const body = JSON.stringify(fields);
  const preview = result?.body === body ? result.value : undefined;
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      void api.previewConfirmation(base.id, JSON.parse(body), base.version).then(
        (value) => {
          if (active) {
            setResult({ body, value });
            setError('');
          }
        },
        (e: unknown) => {
          if (active) {
            setResult(undefined);
            setError(toAppError(e).message);
          }
        },
      );
    }, 300);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [api, base.id, base.version, body]);
  const submit = async () => {
    if (
      busy ||
      conflict ||
      (!retry && (!preview || preview.checks.some((c) => c.status === 'block')))
    )
      return;
    setBusy(true);
    setError('');
    key.current ??= newIdempotencyKey();
    try {
      await api.confirmRequisition(base.id, fields, base.version, { idempotencyKey: key.current });
      onSuccess();
    } catch (e) {
      const err = toAppError(e);
      const uncertain = err.status === 0 || err.status >= 500;
      setRetry(uncertain);
      if (!uncertain) key.current = undefined;
      setConflict(err.status === 409);
      setError(
        err.message + (err.status === 409 ? '。修改内容已保留，请关闭并刷新详情后重新核对。' : ''),
      );
      if (!uncertain) setResult(undefined);
    } finally {
      setBusy(false);
    }
  };
  return {
    fields,
    preview,
    error,
    busy,
    locked: busy || retry || conflict,
    canSubmit:
      !busy &&
      !conflict &&
      (retry || (!!preview && !preview.checks.some((c) => c.status === 'block'))),
    retry,
    submit,
    changeReporting: (id: string, name: string) =>
      setFields((old) => ({ ...old, reportToId: id, reportTo: name })),
    change: (name: string, value: string) => setFields((old) => ({ ...old, [name]: value })),
  };
}
