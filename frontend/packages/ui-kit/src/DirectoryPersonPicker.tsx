import { ActionButton } from './controls';
import { useEffect, useState } from 'react';
import { useApi, toAppError, type ApiClient } from '@recruiter/api-client';

type Result = Awaited<ReturnType<ApiClient['formUsers']>>;

/** Shared directory selection preserves native select semantics across desktop and mobile. */
export function DirectoryPersonPicker({
  id,
  label,
  dept,
  value,
  legacyName,
  multiple = false,
  disabled = false,
  requisitionId,
  onChange,
}: {
  id: string;
  label: string;
  dept: string;
  value: string[];
  legacyName?: string;
  multiple?: boolean;
  disabled?: boolean;
  requisitionId?: string;
  onChange: (ids: string[], name: string) => void;
}) {
  const api = useApi();
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{ key: string; data?: Result; error?: string }>();
  const key = JSON.stringify([dept, query, page, value, requisitionId, revision]);
  const current = state?.key === key ? state : undefined;
  useEffect(() => {
    if (!dept) return;
    let active = true;
    const [department, search, number, selected, reqId] = JSON.parse(key) as [
      string,
      string,
      number,
      string[],
      string?,
    ];
    const timer = setTimeout(() => {
      void api.formUsers(department, search, number, selected, reqId).then(
        (data) => {
          if (active) setState({ key, data });
        },
        (error: unknown) => {
          if (active) setState({ key, error: toAppError(error).message });
        },
      );
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [api, dept, key]);
  const data = current?.data;
  const selected =
    data?.selected ?? value.map((uid) => ({ id: uid, name: null, available: false }));
  const options = new Map((data?.items ?? []).map((u) => [u.id, u]));
  for (const user of selected)
    if (user.available && user.name) options.set(user.id, { id: user.id, name: user.name });
  const unavailable = !!data && selected.some((u) => !u.available);
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <input
        aria-label={`搜索${label}`}
        placeholder="搜索姓名或账号"
        maxLength={100}
        value={query}
        disabled={disabled || !dept}
        style={{ width: '100%', boxSizing: 'border-box', padding: 8 }}
        onChange={(e) => {
          setQuery(e.target.value);
          setPage(1);
        }}
      />
      <select
        id={id}
        value={multiple ? '' : (value[0] ?? '')}
        disabled={disabled || !data || !dept || (multiple && value.length >= 50)}
        style={{ width: '100%', minHeight: 40, padding: 8 }}
        onChange={(e) => {
          const uid = e.target.value;
          if (multiple && !uid) return;
          onChange(
            multiple ? [...new Set([...value, uid])] : uid ? [uid] : [],
            options.get(uid)?.name ?? '',
          );
        }}
      >
        <option value="">{multiple ? '添加可见人员' : '请选择人员'}</option>
        {!multiple && value[0] && !options.has(value[0]) && (
          <option value={value[0]} disabled>
            {legacyName || value[0]}（待核验）
          </option>
        )}
        {[...options.values()]
          .filter((u) => !multiple || !value.includes(u.id))
          .map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}（{u.id}）
            </option>
          ))}
      </select>
      {!value.length && legacyName && (
        <span role="status">历史值：{legacyName}，请重新选择人员</span>
      )}
      {multiple &&
        selected.map((u) => (
          <div key={u.id} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span>
              {u.name ?? u.id}
              {data && !u.available ? '（已失效或超出范围）' : ''}
            </span>
            <ActionButton
              type="button"
              disabled={disabled}
              onClick={() =>
                onChange(
                  value.filter((uid) => uid !== u.id),
                  '',
                )
              }
              aria-label={`移除 ${u.name ?? u.id}`}
            >
              移除
            </ActionButton>
          </div>
        ))}
      {!dept ? (
        <span>请先选择需求部门</span>
      ) : !current ? (
        <span role="status">正在加载人员目录…</span>
      ) : current.error ? (
        <div role="alert">
          {current.error}{' '}
          <ActionButton type="button" disabled={disabled} onClick={() => setRevision((v) => v + 1)}>
            重试人员目录
          </ActionButton>
        </div>
      ) : (
        <>
          {unavailable && (
            <span role="status">
              已选人员已失效或超出部门范围，请重新选择；审批中的未修改历史值保留原快照。
            </span>
          )}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <ActionButton
              type="button"
              disabled={disabled || page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页人员
            </ActionButton>
            <span>
              第 {page} 页 · {data?.total ?? 0} 人
            </span>
            <ActionButton
              type="button"
              disabled={disabled || page * 20 >= (data?.total ?? 0)}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页人员
            </ActionButton>
          </div>
        </>
      )}
    </div>
  );
}
