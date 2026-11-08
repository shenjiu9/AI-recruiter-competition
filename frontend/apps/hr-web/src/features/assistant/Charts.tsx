import { CheckCircleFilled, RollbackOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useReliableWrite, type AssistantAction, type AssistantBlock } from '@recruiter/api-client';
import { useRunAction } from './actions';
import { useAssistant } from './state';

type Of<T extends AssistantBlock['type']> = Extract<AssistantBlock, { type: T }>;

const pct = (v: number, max: number) => `${max > 0 ? Math.min(100, (v / max) * 100) : 0}%`;

function Head({ title, href, extra }: { title?: string; href?: string; extra?: string }) {
  if (!title) return null;
  return (
    <div className="as-card-h">
      <span className="as-card-title">{title}</span>
      {extra && <span className="as-muted num">{extra}</span>}
      {href && (
        <Link className="as-link as-push" to={href}>
          打开详情
        </Link>
      )}
    </div>
  );
}

/** 漏斗：每一级显示人数和相对上一级的转化率 */
export function Funnel({ block }: { block: Of<'funnel'> }) {
  const max = Math.max(1, ...block.items.map((i) => i.value));
  return (
    <div className="as-card" aria-label={block.title ?? '候选人阶段分布'}>
      <Head title={block.title} />
      <div className="as-funnel">
        {block.items.map((s, i) => {
          const prev = i > 0 ? (block.items[i - 1]?.value ?? 0) : 0;
          return (
            <div key={s.label} className="as-funnel-row">
              <span className="as-funnel-l">{s.label}</span>
              <span className="as-funnel-bar">
                <span style={{ width: pct(s.value, max) }} />
              </span>
              <span className="as-funnel-v num">{s.value}</span>
              <span className="as-funnel-c num">
                {i > 0 && prev > 0 ? `${Math.round((s.value / prev) * 100)}%` : ''}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** 进度条：已完成 / 目标，例如已录用 / 计划招聘 */
export function Progress({ block }: { block: Of<'progress'> }) {
  const { send } = useAssistant();
  if (!block.items.length) return null;
  return (
    <div className="as-card" aria-label={block.title}>
      <Head title={block.title} href={block.more_href} />
      <ul className="as-progress">
        {block.items.map((p) => (
          <li key={p.label}>
            <div className="as-progress-h">
              {p.ask ? (
                <button type="button" className="as-row-title" onClick={() => send(p.ask!)}>
                  {p.label}
                </button>
              ) : (
                <span className="as-progress-l">{p.label}</span>
              )}
              <span className="num as-progress-v">
                {p.value}/{p.total}
              </span>
              <span className="as-muted as-push">{p.note}</span>
            </div>
            <div
              className={`as-progress-bar as-bar-${p.tone || 'brand'}`}
              role="progressbar"
              aria-label={p.label}
              aria-valuemin={0}
              aria-valuemax={p.total}
              aria-valuenow={p.value}
            >
              <span style={{ width: pct(p.value, p.total) }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 横向柱状图：原因、来源、按天的数量 */
export function Bars({ block }: { block: Of<'bar'> }) {
  if (!block.items.length) return null;
  const max = Math.max(1, ...block.items.map((i) => i.value));
  return (
    <div className="as-card" aria-label={block.title}>
      <Head title={block.title} />
      <div className="as-bars">
        {block.items.map((b) => (
          <div key={b.label} className="as-bars-row">
            <span className="as-bars-l">{b.label}</span>
            <span className={`as-bars-bar as-bar-${b.tone || 'brand'}`}>
              <span style={{ width: pct(b.value, max) }} />
            </span>
            <span className="as-bars-v num">
              {b.value}
              {block.unit && <small> {block.unit}</small>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 占比条：一条分段条加图例 */
export function Stack({ block }: { block: Of<'stack'> }) {
  const total = block.items.reduce((n, i) => n + i.value, 0);
  if (!total) return null;
  return (
    <div className="as-card" aria-label={block.title}>
      <Head title={block.title} extra={`共 ${total}`} />
      <div
        className="as-stack"
        role="img"
        aria-label={block.items.map((i) => `${i.label} ${i.value}`).join('，')}
      >
        {block.items.map((s, i) => (
          <span
            key={s.label}
            className={`as-stack-seg as-seg-${s.tone || 'p' + (i % 5)}`}
            style={{ flexGrow: s.value }}
            title={`${s.label} ${s.value}`}
          />
        ))}
      </div>
      <ul className="as-legend">
        {block.items.map((s, i) => (
          <li key={s.label}>
            <span className={`as-dot as-seg-${s.tone || 'p' + (i % 5)}`} aria-hidden />
            {s.label}
            <span className="num as-legend-v">{s.value}</span>
            <span className="as-muted num">{Math.round((s.value / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 趋势：按周的柱形 */
export function Trend({ block }: { block: Of<'trend'> }) {
  const n = block.items.length;
  if (!n) return null;
  const max = Math.max(1, ...block.items.map((i) => i.value));
  const w = 640;
  const h = 140;
  const step = w / n;
  const y = (v: number) => h - 4 - (v / max) * (h - 24);
  const sum = block.items.reduce((a, p) => a + p.value, 0);
  return (
    <div className="as-card" aria-label={block.title}>
      <Head title={block.title} extra={`近 ${n} 周共 ${sum} ${block.unit}`} />
      <svg
        className="as-trend"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label={block.items.map((p) => `${p.label} ${p.value}${block.unit}`).join('，')}
      >
        {block.items.map((p, i) => (
          <g key={p.label}>
            <rect
              className="as-trend-col"
              x={i * step + step * 0.22}
              width={step * 0.56}
              y={y(p.value)}
              height={h - 4 - y(p.value)}
              rx={2}
            />
            {p.value > 0 && (
              <text className="as-trend-v" x={i * step + step / 2} y={y(p.value) - 5}>
                {p.value}
              </text>
            )}
          </g>
        ))}
      </svg>
      <div className="as-trend-x">
        {block.items.map((p) => (
          <span key={p.label} className="num">
            {p.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/** 时间线：应聘进程、审批进程 */
export function Timeline({ block }: { block: Of<'timeline'> }) {
  return (
    <div className="as-card" aria-label={block.title}>
      <Head title={block.title} href={block.href} />
      <ol className="as-timeline">
        {block.items.map((s, i) => (
          <li
            key={i}
            className={`as-tl-${s.state}`}
            aria-current={s.state === 'current' ? 'step' : undefined}
          >
            <span className="as-tl-dot" aria-hidden />
            <div className="as-tl-body">
              <span className="as-tl-title">{s.title}</span>
              {s.time && <span className="as-muted num">{s.time}</span>}
              {s.subtitle && <div className="as-row-sub">{s.subtitle}</div>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function Chat({ block }: { block: Of<'chat'> }) {
  return (
    <div className="as-card" aria-label={block.title}>
      <div className="as-card-h">
        <span className="as-card-title">{block.title}</span>
        <span className="as-tag as-tone-muted">{block.mode}</span>
        <Link className="as-link as-push" to={block.href}>
          打开会话
        </Link>
      </div>
      {block.items.length === 0 ? (
        <p className="as-muted">还没有消息。</p>
      ) : (
        <ul className="as-chatlog">
          {block.items.map((m) => (
            <li key={m.id} className={`as-chatlog-${m.sender === 'candidate' ? 'in' : 'out'}`}>
              <div className="as-chatlog-meta">
                {m.label} · <span className="num">{m.time}</span>
                {m.status !== 'sent' && (
                  <span className="as-tag as-tone-warning">
                    {m.status === 'queued' ? '排队中' : m.status}
                  </span>
                )}
              </div>
              <div className="as-chatlog-bubble">{m.content}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Table({ block }: { block: Of<'table'> }) {
  return (
    <div className="as-card" aria-label={block.title}>
      <Head title={block.title} href={block.more_href} />
      <div className="as-table-wrap">
        <table className="as-table">
          <thead>
            <tr>
              {block.columns.map((c) => (
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((r, i) => (
              <tr key={i}>
                {r.map((v, j) => (
                  <td key={j} className={typeof v === 'number' ? 'num' : undefined}>
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** 已直接执行的小操作：说明结果，可一键撤销（同样走现有接口） */
export function Done({ block }: { block: Of<'done'> }) {
  const runAction = useRunAction();
  const [undone, setUndone] = useState('');
  const op = useReliableWrite(
    (a: AssistantAction, opts) => runAction(a, { reason: '在 AI 助手中撤销' }, opts),
    () => setUndone(`已撤销：${block.title}`),
  );
  return (
    <div className="as-card as-card-done" aria-label={block.title}>
      <div className="as-card-h">
        <CheckCircleFilled aria-hidden className="as-ok-icon" />
        <span className="as-card-title">{block.title}</span>
        <span className={`as-tag ${undone ? 'as-tone-muted' : 'as-tone-success'}`}>
          {undone ? '已撤销' : '已执行'}
        </span>
        {block.undo && !undone && (
          <Button
            size="small"
            className="as-push"
            icon={<RollbackOutlined aria-hidden />}
            loading={op.busy}
            disabled={op.locked}
            onClick={() => void op.submit(block.undo!.action)}
          >
            {block.undo.label}
          </Button>
        )}
      </div>
      {(undone ? [undone] : block.lines).map((l) => (
        <p key={l} className="as-muted">
          {l}
        </p>
      ))}
      {op.error && (
        <p role="alert" className="as-error">
          {op.error}
        </p>
      )}
    </div>
  );
}
