import { CheckCircleFilled, ExclamationCircleOutlined } from '@ant-design/icons';
import { Button, Checkbox, Input, Select } from 'antd';
import { useState } from 'react';
import { useReliableWrite, type AssistantAction } from '@recruiter/api-client';
import { needsReason, useRunAction } from './actions';
import { useAssistant } from './state';

const REJECT_REASONS = [
  { value: 'requirements', label: '不符合职业要求' },
  { value: 'experience', label: '经验不足' },
  { value: 'skills', label: '技能不匹配' },
  { value: 'salary', label: '薪资不匹配' },
  { value: 'location', label: '地点不匹配' },
  { value: 'other', label: '其他' },
] as const;
type RejectCode = (typeof REJECT_REASONS)[number]['value'];
interface Props {
  title: string;
  lines: string[];
  quote?: string;
  action: AssistantAction;
  reason?: string;
  danger?: boolean;
  onCancel?: () => void;
}

/**
 * 助手提出的操作。确认后调用和页面按钮完全相同的接口：权限、版本号、幂等和审计都不变；
 * 版本已变化时由接口拒绝，提示重新问一次助手拿最新状态。
 */
export function ConfirmCard({
  title,
  lines,
  quote,
  action,
  reason: initial = '',
  danger,
  onCancel,
}: Props) {
  const runAction = useRunAction();
  const { send } = useAssistant();
  const [reason, setReason] = useState(initial);
  const [code, setCode] = useState<RejectCode | undefined>();
  const [notify, setNotify] = useState(false);
  const [done, setDone] = useState('');
  const [cancelled, setCancelled] = useState(false);

  const op = useReliableWrite(
    (body: AssistantAction, opts) => runAction(body, { reason, code, notify }, opts),
    (message) => setDone(message),
  );

  if (cancelled) return <p className="as-muted as-cancelled">已取消：{title}</p>;
  if (done)
    return (
      <div className="as-card as-card-done">
        <CheckCircleFilled aria-hidden className="as-ok-icon" /> {done}
      </div>
    );
  const needsCode = action.kind === 'reject';
  const ready = (!needsReason(action) || !!reason.trim()) && (!needsCode || !!code);
  return (
    <div
      className={`as-card as-confirm${danger ? ' as-confirm-danger' : ''}`}
      role="group"
      aria-label={title}
    >
      <div className="as-card-h">
        <ExclamationCircleOutlined
          aria-hidden
          className={danger ? 'as-bad-icon' : 'as-warn-icon'}
        />
        <span className="as-card-title">{title}</span>
        <span className="as-tag as-tone-warning">待你确认</span>
      </div>
      {quote && <blockquote className="as-quote">{quote}</blockquote>}
      {lines.length > 0 && (
        <ul className="as-lines">
          {lines.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      )}
      {needsCode && (
        <Select
          aria-label="淘汰原因分类"
          placeholder="选择淘汰原因"
          value={code}
          onChange={setCode}
          options={[...REJECT_REASONS]}
          disabled={op.locked}
          style={{ width: '100%' }}
        />
      )}
      {needsReason(action) && (
        <Input
          aria-label="操作原因"
          placeholder="填写原因（写入审计记录）"
          value={reason}
          maxLength={500}
          onChange={(e) => setReason(e.target.value)}
          disabled={op.locked}
        />
      )}
      {needsCode && (
        <Checkbox
          checked={notify}
          onChange={(e) => setNotify(e.target.checked)}
          disabled={op.locked}
        >
          通知候选人（在可联系时段发送）
        </Checkbox>
      )}
      <div className="as-actions">
        <Button
          type="primary"
          danger={danger}
          disabled={op.locked || !ready}
          loading={op.busy}
          onClick={() => void op.submit(action)}
        >
          确认{action.kind === 'message' ? '发送' : '执行'}
        </Button>
        <Button
          disabled={op.busy}
          onClick={() => {
            setCancelled(true);
            onCancel?.();
          }}
        >
          取消
        </Button>
      </div>
      {op.error && (
        <p role="alert" className="as-error">
          {op.error}
          {op.conflict || /刷新|已更新|变化/.test(op.error)
            ? '（数据已变化，可以重新问我一次拿到最新状态）'
            : ''}
        </p>
      )}
      {op.retry && (
        <Button size="small" onClick={op.retryAction}>
          重试同一次提交
        </Button>
      )}
      {(op.conflict || /刷新|已更新/.test(op.error)) && (
        <Button
          size="small"
          type="link"
          onClick={() => send(title.replace(/ · .*/, '').replace(/^(推进|淘汰) /, '$1'))}
        >
          重新获取最新状态
        </Button>
      )}
    </div>
  );
}
