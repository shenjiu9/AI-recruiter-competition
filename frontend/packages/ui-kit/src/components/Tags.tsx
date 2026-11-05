import { Tooltip } from 'antd';
import {
  CONFIDENCE_LABEL,
  confidenceBand,
  endResultLabel,
  healthLabel,
  levelLabel,
  sourceLabel,
  stageLabel,
  type EndResult,
  type EvidenceRef,
  type FieldSource,
  type HealthLevel,
  type Level,
  type Stage,
} from '@recruiter/domain';

/** AI 产出标记：文字 + AI 青，不用星光图标 */
export function AiTag({ children = 'AI' }: { children?: string }) {
  return <span className="rc-tag rc-ai">{children}</span>;
}

export function LevelTag({ level }: { level: Level }) {
  return (
    <span className="rc-tag rc-level" data-level={level}>
      {levelLabel(level)}
    </span>
  );
}

/** 把握度：高 / 中 / 低三档，形状 + 文字 + 颜色；偏低时悬停显示原因 */
export function ConfidenceTag({ value, reasons, showValue = true }: { value: number; reasons?: string[]; showValue?: boolean }) {
  const band = confidenceBand(value);
  const tag = (
    <span className="rc-conf" data-band={band} aria-label={`${CONFIDENCE_LABEL[band]} ${value.toFixed(2)}`}>
      <span className="shape" aria-hidden />
      {CONFIDENCE_LABEL[band]}
      {showValue && <span className="val">{value.toFixed(2)}</span>}
    </span>
  );
  return reasons?.length ? <Tooltip title={`把握偏低：${reasons.join('；')}`}>{tag}</Tooltip> : tag;
}

export function StageBadge({ stage, ended }: { stage: Stage; ended?: EndResult }) {
  return (
    <span className="rc-tag rc-stage" data-ended={!!ended}>
      {ended ? endResultLabel(ended) : stageLabel(stage)}
    </span>
  );
}

export function FieldSourceTag({ source, detail }: { source: FieldSource; detail?: string }) {
  const tag = (
    <span className="rc-tag rc-src" data-src={source}>
      {sourceLabel(source)}
    </span>
  );
  return detail ? <Tooltip title={detail}>{tag}</Tooltip> : tag;
}

const HEALTH_MARK: Record<HealthLevel, string> = { risk: '▲', watch: '◆', ok: '●' };
export function HealthTag({ level }: { level: HealthLevel }) {
  return (
    <span className="rc-health" data-h={level}>
      <span aria-hidden>{HEALTH_MARK[level]}</span>
      {healthLabel(level)}
    </span>
  );
}

const EV_KIND: Record<EvidenceRef['kind'], string> = { resume: '简历', message: '会话', feedback: '面评', rule: '规则' };
/** 证据引用：点击展开原文或在简历中定位 */
export function EvidenceChip({ ev, pressed, onClick }: { ev: EvidenceRef; pressed?: boolean; onClick?: () => void }) {
  return (
    <button type="button" className="rc-ev" aria-pressed={!!pressed} onClick={onClick} title={`${EV_KIND[ev.kind]}原文：${ev.quote}`}>
      {ev.ref}
    </button>
  );
}

export function EvidenceQuote({ ev }: { ev: EvidenceRef }) {
  return (
    <div className="rc-quote">
      <div className="ref">
        {EV_KIND[ev.kind]} {ev.ref}
      </div>
      {ev.quote}
    </div>
  );
}
