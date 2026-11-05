import type React from 'react';
import { Button, Dialog, Space } from 'antd-mobile';
import { useNavigate } from 'react-router-dom';
import { formatDue } from '@recruiter/domain';
import type { BizInboxItem } from '@recruiter/api-client';
import { track } from '@recruiter/telemetry';
import { useInboxAct } from './api';

const KIND = { requisition_approval: '待我审批', hire_decision: '待我决定', recommendation: '待我决定', feedback: '待我面评' } as const;

/** 待办列表：每张卡片上能直接完成主操作，复杂操作才进详情（PRD 15.4） */
export function InboxList({ items }: { items: BizInboxItem[] }) {
  const nav = useNavigate();
  const act = useInboxAct();
  const doAct = (it: BizInboxItem, action: string) => {
    act.mutate({ id: it.id, action });
    track('im_card_action', { card_type: it.kind, action });
  };
  if (!items.length) return <div className="rm-card"><h2>没有待办</h2><div className="rm-sub">需要你审批、决定或写面评的事会出现在这里，也会通过飞书消息提醒你。</div></div>;
  return (
    <>
      {items.map((it) => {
        const due = formatDue(it.dueAt);
        return (
          <article key={it.id} className="rm-card" aria-labelledby={`t-${it.id}`}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--rm-ink-3)', marginBottom: 6 }}>
              <span>{KIND[it.kind]}</span>
              <span style={{ color: due.urgent ? 'var(--adm-color-warning)' : undefined }}>{due.overdue ? '已超时' : `${due.text} 前`}</span>
            </div>
            <h2 id={`t-${it.id}`}>{it.title}</h2>
            <div className="rm-sub">{it.detail}</div>
            {it.done ? (
              <div style={{ marginTop: 12, color: 'var(--adm-color-success)' }}>已处理：{it.done}</div>
            ) : (
              <Space block direction="vertical" style={{ marginTop: 12, '--gap': '8px' } as React.CSSProperties}>
                {it.kind === 'recommendation' && (
                  <>
                    <Button block color="primary" size="large" onClick={() => doAct(it, '想见')}>想见，安排复试</Button>
                    <Space block style={{ '--gap': '8px' } as React.CSSProperties} justify="between">
                      <Button size="large" onClick={() => nav(`/brief/${it.applicationId}`)}>看推荐理由</Button>
                      <Button size="large" onClick={() => Dialog.confirm({ content: '确定不合适？HR 会按流程处理并通知候选人。', confirmText: '不合适', cancelText: '返回', onConfirm: () => doAct(it, '不合适') })}>不合适</Button>
                    </Space>
                  </>
                )}
                {it.kind === 'requisition_approval' && (
                  <>
                    <Button block color="primary" size="large" onClick={() => doAct(it, '已通过')}>通过</Button>
                    <Button block size="large" onClick={() => nav('/')}>驳回或转交（打开详情）</Button>
                  </>
                )}
                {it.kind === 'feedback' && (
                  <Button block color="primary" size="large" onClick={() => nav(`/feedback/${it.applicationId}`)}>写面评</Button>
                )}
              </Space>
            )}
          </article>
        );
      })}
    </>
  );
}
