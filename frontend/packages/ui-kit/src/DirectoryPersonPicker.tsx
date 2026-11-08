import { Select, Tag } from 'antd';
import { ActionButton } from './controls';
import { useEffect, useState } from 'react';
import { useApi, toAppError, type ApiClient } from '@recruiter/api-client';

type Result = Awaited<ReturnType<ApiClient['formUsers']>>;

/** Search and select in one control; reporting is single-owner, visibility is multi-select. */
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
      <Select
        id={id}
        aria-label={`搜索${label}`}
        showSearch
        virtual={false}
        allowClear
        mode={multiple ? 'multiple' : undefined}
        placeholder={multiple ? `搜索并勾选${label}（可多选）` : `搜索并选择一位${label}`}
        value={multiple ? value : value[0] || undefined}
        searchValue={query}
        filterOption={false}
        loading={!!dept && !current}
        disabled={disabled || !dept}
        style={{ width: '100%', minWidth: 0 }}
        onSearch={(text) => {
          setQuery(text);
          setPage(1);
        }}
        onChange={(next: string | string[] | undefined) => {
          const ids = Array.isArray(next) ? next : next ? [next] : [];
          if (ids.length > 50) return;
          onChange(ids, options.get(ids[0] ?? '')?.name ?? '');
          setQuery('');
          setPage(1);
        }}
        options={[
          ...[...options.values()].map((u) => ({ value: u.id, label: `${u.name}（${u.id}）` })),
          ...selected
            .filter((u) => !options.has(u.id))
            .map((u) => ({
              value: u.id,
              label: `${u.name ?? legacyName ?? u.id}${data && !u.available ? '（已失效或超出范围）' : '（待核验）'}`,
              disabled: true,
            })),
        ]}
        optionRender={(option) => (
          <span>
            {multiple ? (value.includes(String(option.value)) ? '☑ ' : '☐ ') : ''}
            {option.label}
          </span>
        )}
        tagRender={({ value: uid, label: text }) => (
          <Tag style={{ whiteSpace: 'normal', maxWidth: '100%' }}>
            <span>{text}</span>
            {!disabled && (
              <button
                type="button"
                aria-label={`移除 ${selected.find((u) => u.id === uid)?.name ?? uid}`}
                disabled={disabled}
                onMouseDown={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
                onClick={() => {
                  const next = value.filter((id) => id !== uid);
                  onChange(next, options.get(next[0] ?? '')?.name ?? '');
                }}
              >
                ×
              </button>
            )}
          </Tag>
        )}
      />
      {!multiple && (
        <span className="muted">
          {label === '汇报对象'
            ? '汇报对象只选一位；审批人按审批链依次处理。多人可见请在保密需求的「可见人员」中选择。'
            : `${label}只选一位。`}
        </span>
      )}
      {!value.length && legacyName && (
        <span role="status">历史值：{legacyName}，请重新选择人员</span>
      )}
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
