import { ActionButton } from './controls';
import { useEffect, useRef, useState } from 'react';
import './ApprovalTransfer.css';
import {
  newIdempotencyKey,
  toAppError,
  useApi,
  type RequisitionDetail,
} from '@recruiter/api-client';

/** Both clients pin the request version and freeze uncertain writes for same-key retries. */
export function ApprovalTransfer({
  req,
  onSuccess,
}: {
  req: RequisitionDetail;
  onSuccess: () => void;
}) {
  const api = useApi();
  const [base] = useState(req);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [candidates, setCandidates] = useState<{ id: string; name: string }[]>([]);
  const [total, setTotal] = useState(0);
  const [target, setTarget] = useState<{ id: string; name: string }>();
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [searchError, setSearchError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [retry, setRetry] = useState(false);
  const key = useRef<string>();
  const inFlight = useRef(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    const timer = setTimeout(() => {
      void api.transferCandidates(base.id, query, page).then(
        (result) => {
          if (!active) return;
          setCandidates(result.items);
          setTotal(result.total);
          setSearchError('');
          setLoading(false);
          if (result.version !== base.version) {
            setConflict(true);
            setError('需求已被修改。输入已保留，请关闭并刷新详情后重新核对。');
          }
        },
        (e: unknown) => {
          if (active) {
            setSearchError(toAppError(e).message);
            setLoading(false);
          }
        },
      );
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [api, base.id, base.version, query, page]);
  const locked = busy || retry || conflict;
  const submit = async () => {
    if (!target || !reason.trim() || inFlight.current || conflict) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    key.current ??= newIdempotencyKey();
    try {
      await api.transferRequisition(
        base.id,
        {
          expected_version: base.version,
          node_id: base.chain[base.currentNode]!.id,
          target_id: target.id,
          reason,
        },
        { idempotencyKey: key.current },
      );
      onSuccess();
    } catch (e) {
      const err = toAppError(e);
      const uncertain = err.status === 0 || err.status >= 500;
      setRetry(uncertain);
      if (!uncertain) key.current = undefined;
      setConflict(err.status === 409);
      setError(
        err.message + (err.status === 409 ? '。输入已保留，请关闭并刷新详情后重新核对。' : ''),
      );
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  const options =
    target && !candidates.some((user) => user.id === target.id)
      ? [target, ...candidates]
      : candidates;
  return (
    <form
      className="approval-transfer"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <p>接收人须在职并具备本部门的节点审批权限。转交不会通过或跳过当前节点。</p>
      <label>
        搜索接收人
        <input
          value={query}
          disabled={locked}
          maxLength={100}
          placeholder="姓名或账号"
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
      </label>
      {searchError && <p role="alert">{searchError}</p>}
      <label>
        转交给
        <select
          value={target?.id ?? ''}
          disabled={locked || loading}
          required
          onChange={(e) => setTarget(options.find((user) => user.id === e.target.value))}
        >
          <option value="">{loading ? '正在查询…' : '请选择接收人'}</option>
          {options.map((user) => (
            <option key={user.id} value={user.id}>
              {user.name} ({user.id})
            </option>
          ))}
        </select>
      </label>
      {!loading && !searchError && total === 0 && (
        <p>没有符合权限的接收人，请联系管理员检查配置。</p>
      )}
      {total > 20 && (
        <div>
          <ActionButton
            type="button"
            disabled={locked || loading || page === 1}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </ActionButton>
          <span>
            {' '}
            第 {page} 页 · 共 {total} 人{' '}
          </span>
          <ActionButton
            type="button"
            disabled={locked || loading || page * 20 >= total}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </ActionButton>
        </div>
      )}
      <label>
        转交原因（必填）
        <textarea
          value={reason}
          disabled={locked}
          maxLength={1000}
          required
          rows={3}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      {error && <p role="alert">{error}</p>}
      {retry && <p>尚未收到确定结果，请重试原转交请求。</p>}
      <ActionButton
        type="submit"
        disabled={
          busy || conflict || !target || !reason.trim() || (!retry && (loading || !!searchError))
        }
      >
        {busy ? '正在转交…' : retry ? '重试转交' : '确认转交'}
      </ActionButton>
    </form>
  );
}
