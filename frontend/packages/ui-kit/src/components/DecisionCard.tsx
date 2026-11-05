import { CheckCircleOutlined, StopOutlined } from '@ant-design/icons';
import { App, Button, Checkbox, Select, Space } from 'antd';
import { forwardRef, useImperativeHandle, useMemo, useState, type ReactNode } from 'react';
import {
  REJECT_REASONS,
  cardTypeLabel,
  confidenceBand,
  formatDue,
  type CardOption,
  type DecisionCard as Card,
  type EvidenceRef,
} from '@recruiter/domain';
import { ConfidenceTag, EvidenceChip, EvidenceQuote, LevelTag } from './Tags';

export interface ResolveExtras {
  rejectReason?: string;
  selected?: string[];
}

export interface DecisionCardHandle {
  confirmPrimary: () => void;
  openReject: () => void;
  toggleEvidence: (reasonIndex: number) => void;
}

export interface DecisionCardProps {
  card: Card;
  onResolve: (option: CardOption, extras: ResolveExtras) => Promise<void>;
  /** 点击简历证据时的外部处理（如在候选人详情中定位简历段落）；不传则就地展开原文 */
  onEvidence?: (ev: EvidenceRef) => void;
  extra?: ReactNode;
  showKeyboardHints?: boolean;
}

/**
 * 决策卡：整个产品的核心组件（PRD 5.3）。
 * 标题 → AI 建议与把握 → 不超过 3 条理由（证据可展开）→ 选项 → 时限。超时不会自动执行。
 */
export const DecisionCard = forwardRef<DecisionCardHandle, DecisionCardProps>(function DecisionCard(
  { card, onResolve, onEvidence, extra, showKeyboardHints },
  ref,
) {
  const { modal } = App.useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const [openEv, setOpenEv] = useState<string | null>(null);
  const lockedIds = useMemo(() => new Set(card.batch?.filter((b) => confidenceBand(b.confidence) === 'low').map((b) => b.applicationId)), [card.batch]);
  const [selected, setSelected] = useState<string[]>(() => card.batch?.filter((b) => !lockedIds.has(b.applicationId)).map((b) => b.applicationId) ?? []);
  const due = formatDue(card.dueAt);
  const primary = card.options.find((o) => o.primary) ?? card.options[0];
  const rejectOpt = card.options.find((o) => o.danger && !o.primary);
  const state = busy ? 'processing' : card.state;
  const disabled = state !== 'open';

  const run = async (opt: CardOption, extras: ResolveExtras) => {
    setBusy(opt.key);
    try {
      await onResolve(opt, extras);
    } catch {
      // 错误由调用方统一提示（如版本冲突时刷新卡片），这里只恢复按钮状态
    } finally {
      setBusy(null);
    }
  };

  const choose = (opt: CardOption) => {
    if (disabled) return;
    const isBatch = !!card.batch && opt.primary;
    if (isBatch) {
      const picked = card.batch!.filter((b) => selected.includes(b.applicationId));
      if (!picked.length) return;
      const bands = picked.reduce<Record<string, number>>((m, b) => ((m[confidenceBand(b.confidence)] = (m[confidenceBand(b.confidence)] ?? 0) + 1), m), {});
      modal.confirm({
        title: `淘汰 ${picked.length} 位候选人？`,
        width: 480,
        content: (
          <div>
            <p>{opt.confirm}</p>
            <p style={{ marginTop: 8 }}>
              人员：{picked.map((b) => b.candidateName).join('、')}
              <br />
              把握分布：高 {bands.high ?? 0} 人，中 {bands.mid ?? 0} 人
            </p>
          </div>
        ),
        okText: `淘汰 ${picked.length} 人`,
        okButtonProps: { danger: true },
        cancelText: '返回',
        onOk: () => run(opt, { selected: picked.map((b) => b.applicationId) }),
      });
      return;
    }
    if (opt.confirm || (opt.danger && !opt.primary)) {
      let reason: string | undefined;
      modal.confirm({
        title: `${opt.label}？`,
        content: (
          <div>
            {opt.confirm && <p>{opt.confirm}</p>}
            {!opt.primary && (
              <div style={{ marginTop: 12 }}>
                <div style={{ marginBottom: 4 }}>为什么不采纳 AI 的建议（选填，用于改进评估）</div>
                <Select style={{ width: '100%' }} allowClear placeholder="选择原因" options={REJECT_REASONS.map((r) => ({ value: r, label: r }))} onChange={(v: string) => (reason = v)} />
              </div>
            )}
          </div>
        ),
        okText: opt.label,
        okButtonProps: { danger: !!opt.danger },
        cancelText: '返回',
        onOk: () => run(opt, { rejectReason: reason }),
      });
      return;
    }
    void run(opt, {});
  };

  const toggleEvidence = (i: number) => {
    const r = card.reasons[i];
    const ev = r?.evidence[0];
    if (!ev) return;
    if (onEvidence && ev.kind === 'resume') onEvidence(ev);
    setOpenEv((cur) => (cur === `${i}-0` ? null : `${i}-0`));
  };

  useImperativeHandle(ref, () => ({
    confirmPrimary: () => primary && choose(primary),
    openReject: () => rejectOpt && choose(rejectOpt),
    toggleEvidence,
  }));

  const primaryLabel = card.batch && primary?.primary ? `${primary.label.replace('选中的人', '')} ${selected.length} 人` : primary?.label;

  return (
    <article className="rc-dcard" data-state={state} aria-labelledby={`${card.id}-title`} aria-busy={state === 'processing'}>
      <header className="rc-dhead">
        <div style={{ minWidth: 0 }}>
          <h2 className="rc-dtitle" id={`${card.id}-title`}>
            {card.title}
          </h2>
          <div className="rc-dmeta">
            <span>
              类型 <b>{cardTypeLabel(card.type)}</b>
            </span>
            <span>
              岗位 <b>{card.positionName}</b>
            </span>
            {card.isKey && <span style={{ color: 'var(--rc-brand)' }}>关键候选人</span>}
          </div>
        </div>
        <div className="rc-ddue">
          时限
          <strong data-urgent={due.urgent}>{due.text}</strong>
          超时只提醒，不会自动执行
        </div>
      </header>

      <div className="rc-suggest">
        <span className="rc-tag rc-ai">AI 建议</span>
        <span className="what">{card.suggestion}</span>
        <ConfidenceTag value={card.confidence} />
        <LevelTag level={card.level} />
        {card.lowReasons?.length ? <span className="rc-lowwhy">把握偏低的原因：{card.lowReasons.join('；')}</span> : null}
      </div>

      <ol className="rc-reasons" aria-label="AI 的理由">
        {card.reasons.slice(0, 3).map((r, i) => (
          <li key={i}>
            <span>{r.text}</span>
            <span className="evs">
              {r.evidence.map((ev, j) => (
                <EvidenceChip
                  key={ev.ref}
                  ev={ev}
                  pressed={openEv === `${i}-${j}`}
                  onClick={() => {
                    if (onEvidence && ev.kind === 'resume') onEvidence(ev);
                    setOpenEv((cur) => (cur === `${i}-${j}` ? null : `${i}-${j}`));
                  }}
                />
              ))}
            </span>
            {r.evidence.map((ev, j) => (openEv === `${i}-${j}` ? <EvidenceQuote key={ev.ref} ev={ev} /> : null))}
          </li>
        ))}
      </ol>

      {card.batch && (
        <div className="rc-batch" role="group" aria-label="批量处理的候选人">
          {card.batch.map((b) => {
            const locked = lockedIds.has(b.applicationId);
            return (
              <div className="rc-batch-row" key={b.applicationId}>
                <Checkbox
                  disabled={locked || disabled}
                  checked={selected.includes(b.applicationId)}
                  onChange={(e) => setSelected((s) => (e.target.checked ? [...s, b.applicationId] : s.filter((x) => x !== b.applicationId)))}
                  aria-label={`选择${b.candidateName}`}
                />
                <span>{b.candidateName}</span>
                <span className="why">{b.reason}</span>
                <ConfidenceTag value={b.confidence} />
                {locked && <span className="locked">把握低，不能批量处理，请打开候选人详情单独判断</span>}
              </div>
            );
          })}
        </div>
      )}

      {state === 'done' && (
        <div className="rc-note ok" role="status">
          <CheckCircleOutlined aria-hidden />
          已处理：{card.resolvedNote}
        </div>
      )}
      {state === 'void' && (
        <div className="rc-note void" role="status">
          <StopOutlined aria-hidden />
          这张卡已失效。{card.voidReason}
        </div>
      )}

      {state !== 'done' && state !== 'void' && (
        <div className="rc-dactions">
          <Space wrap>
            {card.options.map((o) => (
              <Button
                key={o.key}
                type={o.primary ? 'primary' : 'default'}
                danger={o.danger && !o.primary ? true : o.danger && !!card.batch}
                loading={busy === o.key}
                disabled={disabled && busy !== o.key}
                onClick={() => choose(o)}
              >
                {o.primary ? primaryLabel : o.label}
                {showKeyboardHints && o.primary && <span className="rc-kbd">Enter</span>}
                {showKeyboardHints && o === rejectOpt && <span className="rc-kbd">D</span>}
              </Button>
            ))}
            {extra}
          </Space>
          {showKeyboardHints && <span className="hint">J / K 切换，1–3 展开证据</span>}
        </div>
      )}
    </article>
  );
});
