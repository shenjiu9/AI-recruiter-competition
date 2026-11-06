import { useState } from 'react';
import { Button, Dialog, Popup } from 'antd-mobile';
import { useNavigate } from 'react-router-dom';
import { formatDue } from '@recruiter/domain';
import type { BizInboxItem } from '@recruiter/api-client';
import { track } from '@recruiter/telemetry';
import { useInboxAct } from './api';
import { RequisitionReview } from './RequisitionReview';

const KIND = {
  requisition_approval: '待我审批',
  hire_decision: '待我决定',
  recommendation: '待我决定',
  feedback: '待我面评',
} as const;

/** 待办列表：每张卡片上能直接完成主操作，复杂操作才进详情（PRD 15.4） */
export function InboxList({ items }: { items: BizInboxItem[] }) {
  const nav = useNavigate();
  const act = useInboxAct();
  const [reviewId, setReviewId] = useState<string | null>(null);
  const doAct = (it: BizInboxItem, action: string) => {
    act.mutate({ id: it.id, action, version: it.version, nodeId: it.nodeId });
    track('im_card_action', { card_type: it.kind, action });
  };
  if (!items.length)
    return (
      <div className="rm-card">
        <h2>没有待办</h2>
        <div className="rm-sub">
          需要你审批、决定或写面评的事会出现在这里，也会通过飞书消息提醒你。
        </div>
      </div>
    );
  return (
    <>
      {items.map((it) => {
        const due = formatDue(it.dueAt);
        return (
          <article key={it.id} className="rm-card" aria-labelledby={`t-${it.id}`}>
            <div className="rm-card-meta">
              <span>{KIND[it.kind]}</span>
              <span data-urgent={due.urgent || due.overdue}>
                {due.overdue ? '已超时' : `${due.text} 前`}
              </span>
            </div>
            <h2 id={`t-${it.id}`}>{it.title}</h2>
            <div className="rm-sub">{it.detail}</div>
            {it.done ? (
              <div className="rm-done" role="status">
                已处理：{it.done}
              </div>
            ) : (
              <div className="rm-actions">
                {it.kind === 'recommendation' && (
                  <>
                    <Button block color="primary" size="large" onClick={() => doAct(it, '想见')}>
                      想见，安排复试
                    </Button>
                    <div className="rm-actions-pair">
                      <Button size="large" onClick={() => nav(`/brief/${it.applicationId}`)}>
                        看推荐理由
                      </Button>
                      <Button
                        size="large"
                        onClick={() => {
                          void Dialog.confirm({
                            content: '确定不合适？HR 会按流程处理并通知候选人。',
                            confirmText: '不合适',
                            cancelText: '返回',
                            onConfirm: () => doAct(it, '不合适'),
                          });
                        }}
                      >
                        不合适
                      </Button>
                    </div>
                  </>
                )}
                {it.kind === 'requisition_approval' && (
                  <>
                    <Button
                      block
                      color="primary"
                      size="large"
                      disabled={act.isPending}
                      onClick={() => doAct(it, '已通过')}
                    >
                      通过
                    </Button>
                    <Button block size="large" onClick={() => setReviewId(it.id)}>
                      查看需求 / 驳回
                    </Button>
                    {it.nodeId === 'manager' && (
                      <Button block onClick={() => setReviewId(it.id)}>
                        修改并确认
                      </Button>
                    )}
                  </>
                )}
                {it.kind === 'feedback' && (
                  <Button
                    block
                    color="primary"
                    size="large"
                    onClick={() => nav(`/feedback/${it.applicationId}`)}
                  >
                    写面评
                  </Button>
                )}
              </div>
            )}
          </article>
        );
      })}
      <Popup
        visible={reviewId !== null}
        onMaskClick={() => setReviewId(null)}
        bodyStyle={{ maxHeight: '90vh', overflowY: 'auto' }}
      >
        {reviewId && <RequisitionReview id={reviewId} onClose={() => setReviewId(null)} />}
      </Popup>
    </>
  );
}
