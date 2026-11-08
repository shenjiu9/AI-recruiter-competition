import { RightOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  toAppError,
  useApi,
  useReliableWrite,
  type AssistantBlock,
  type AssistantItem,
} from '@recruiter/api-client';
import { ConfirmCard } from './ConfirmCard';
import { JobCard, TASK_NAMES } from './JobCard';
import { useAssistant } from './state';

function Metrics({ block }: { block: Extract<AssistantBlock, { type: 'metrics' }> }) {
  return (
    <div className="as-card">
      {block.title && (
        <div className="as-card-h">
          <span className="as-card-title">{block.title}</span>
          {block.href && (
            <Link className="as-link as-push" to={block.href}>
              打开详情
            </Link>
          )}
        </div>
      )}
      <div className="as-metrics">
        {block.items.map((m) => (
          <div key={m.label} className={`as-metric${m.tone ? ' as-tone-' + m.tone : ''}`}>
            <div className="as-metric-v num">{m.value}</div>
            <div className="as-metric-l">{m.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Funnel({ block }: { block: Extract<AssistantBlock, { type: 'funnel' }> }) {
  const max = Math.max(1, ...block.items.map((i) => i.value));
  return (
    <div className="as-card" aria-label="候选人阶段分布">
      <div className="as-funnel">
        {block.items.map((s) => (
          <div key={s.label} className="as-funnel-row">
            <span className="as-funnel-l">{s.label}</span>
            <span className="as-funnel-bar">
              <span style={{ width: `${(s.value / max) * 100}%` }} />
            </span>
            <span className="as-funnel-v num">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Row({ item }: { item: AssistantItem }) {
  const api = useApi();
  const nav = useNavigate();
  const { send, showJob } = useAssistant();
  const [confirm, setConfirm] = useState<NonNullable<AssistantItem['actions']>[number]>();
  const [error, setError] = useState('');
  const openJob = async () => {
    try {
      const job = await api.aiJob(item.job_id!);
      showJob(job, `这是“${TASK_NAMES[job.component] ?? job.component}”的结果：`);
    } catch (e) {
      setError(toAppError(e).message);
    }
  };
  const primary = item.job_id
    ? { label: '在对话中查看', run: () => void openJob() }
    : item.ask
      ? { label: '问问详情', run: () => send(item.ask!) }
      : item.href
        ? { label: '打开', run: () => nav(item.href) }
        : undefined;
  return (
    <li className="as-row">
      <div className="as-row-main">
        <button
          type="button"
          className="as-row-title"
          disabled={!primary}
          onClick={primary?.run}
          title={primary?.label}
        >
          {item.title}
        </button>
        {item.tag && <span className={`as-tag as-tone-${item.tone || 'muted'}`}>{item.tag}</span>}
        {item.meta && <span className="as-row-meta">{item.meta}</span>}
        {item.href && primary?.label !== '打开' && (
          <Link className="as-row-open" to={item.href} aria-label={`打开 ${item.title}`}>
            <RightOutlined aria-hidden />
          </Link>
        )}
      </div>
      {item.subtitle && <div className="as-row-sub">{item.subtitle}</div>}
      {item.actions && item.actions.length > 0 && !confirm && (
        <div className="as-actions as-actions-sm">
          {item.actions.map((a) => (
            <Button key={a.label} size="small" danger={a.danger} onClick={() => setConfirm(a)}>
              {a.label}
            </Button>
          ))}
        </div>
      )}
      {confirm && (
        <ConfirmCard
          title={`${confirm.label}：${item.title}`}
          lines={['处理后这张决策卡会关闭，操作写入审计记录']}
          action={confirm.action}
          danger={confirm.danger}
          onCancel={() => setConfirm(undefined)}
        />
      )}
      {error && (
        <p role="alert" className="as-error">
          {error}
        </p>
      )}
    </li>
  );
}

function List({ block }: { block: Extract<AssistantBlock, { type: 'list' }> }) {
  if (!block.items.length) return null;
  return (
    <div className="as-card">
      <div className="as-card-h">
        <span className="as-card-title">{block.title}</span>
        <span className="as-muted num">{block.items.length}</span>
        {block.more_href && (
          <Link className="as-link as-push" to={block.more_href}>
            查看全部
          </Link>
        )}
      </div>
      <ul className="as-rows">
        {block.items.map((it) => (
          <Row key={it.id} item={it} />
        ))}
      </ul>
    </div>
  );
}

function Profile({ block }: { block: Extract<AssistantBlock, { type: 'profile' }> }) {
  return (
    <div className="as-card">
      <div className="as-card-h">
        <span className="as-avatar" aria-hidden>
          {block.title.slice(0, 1)}
        </span>
        <span className="as-card-title">{block.title}</span>
        {block.tags.map((t) => (
          <span
            key={t}
            className={`as-tag ${t === '未授权' || t === '不再联系' ? 'as-tone-warning' : 'as-tone-muted'}`}
          >
            {t}
          </span>
        ))}
        <Link className="as-link as-push" to={block.href}>
          候选人档案
        </Link>
      </div>
      <dl className="as-facts">
        {block.items.map((f) => (
          <div key={f.label}>
            <dt>{f.label}</dt>
            <dd>{f.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Choose({ block }: { block: Extract<AssistantBlock, { type: 'choose' }> }) {
  const api = useApi();
  const { showJob } = useAssistant();
  const [picked, setPicked] = useState('');
  const op = useReliableWrite(
    (body: { component: string; object_id: string; prompt: string }, opts) =>
      api.startAiJob(body, opts),
    (job) => showJob(job, `已开始“${TASK_NAMES[job.component]}”，结果出来后请核对原文证据再确认。`),
  );
  return (
    <div className="as-card">
      <div className="as-card-h">
        <span className="as-card-title">
          请选择{TASK_NAMES[block.component] ? `“${TASK_NAMES[block.component]}”的对象` : ''}
        </span>
      </div>
      <div className="as-chips">
        {block.options.map((o) => (
          <Button
            key={o.id}
            size="small"
            type={picked === o.id ? 'primary' : 'default'}
            disabled={op.locked || (!!picked && picked !== o.id)}
            loading={op.busy && picked === o.id}
            onClick={() => {
              setPicked(o.id);
              void op.submit({ component: block.component, object_id: o.id, prompt: block.prompt });
            }}
          >
            {o.label}
          </Button>
        ))}
      </div>
      {op.error && (
        <p role="alert" className="as-error">
          {op.error}
        </p>
      )}
      {op.retry && (
        <Button size="small" onClick={op.retryAction}>
          重试同一次提交
        </Button>
      )}
    </div>
  );
}

export function Block({ block }: { block: AssistantBlock }) {
  switch (block.type) {
    case 'metrics':
      return <Metrics block={block} />;
    case 'funnel':
      return <Funnel block={block} />;
    case 'list':
      return <List block={block} />;
    case 'profile':
      return <Profile block={block} />;
    case 'confirm':
      return <ConfirmCard {...block} />;
    case 'job':
      return <JobCard initial={block.job} />;
    case 'choose':
      return <Choose block={block} />;
    default:
      return null;
  }
}
