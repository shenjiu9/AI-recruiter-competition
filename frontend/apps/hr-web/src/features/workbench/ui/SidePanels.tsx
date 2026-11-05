import { App, Input } from 'antd';
import { Link } from 'react-router-dom';
import type { AiActivity, PositionHealth } from '@recruiter/domain';
import { AiActivityItem, HealthTag } from '@recruiter/ui-kit';
import { useCorrectAction, useUndoAction } from '../api';

export function HealthPanel({ items }: { items: PositionHealth[] }) {
  return (
    <section className="panel" aria-labelledby="health-h">
      <div className="panel-h" id="health-h">岗位健康</div>
      <div className="panel-b">
        {items.map((p) => (
          <Link key={p.positionId} to={`/positions/${p.positionId}`} style={{ display: 'block', padding: '10px 0', borderBottom: '1px solid var(--rc-line)', color: 'inherit' }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <HealthTag level={p.health} />
              <span style={{ fontWeight: 500 }}>{p.name}</span>
              <span className="num muted" style={{ marginLeft: 'auto', fontSize: 12 }}>可招 {p.openings} / {p.total}</span>
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{p.why}</div>
          </Link>
        ))}
      </div>
    </section>
  );
}

export function ActivityPanel({ items }: { items: AiActivity[] }) {
  const undo = useUndoAction();
  const correct = useCorrectAction();
  const { modal } = App.useApp();
  return (
    <section className="panel" aria-labelledby="act-h" id="ai-activity">
      <div className="panel-h" id="act-h">
        AI 动态
        <span className="muted" style={{ marginLeft: 'auto', fontWeight: 400, fontSize: 12 }}>今日抽检 5 条待看</span>
      </div>
      <div className="panel-b">
        {items.map((a) => (
          <AiActivityItem
            key={a.actionId}
            a={a}
            onUndo={() =>
              modal.confirm({
                title: '撤销这个动作？',
                content: `${a.text}。撤销后对象会恢复到动作前的状态，操作记录会保留撤销痕迹。`,
                okText: '撤销',
                cancelText: '返回',
                onOk: () => undo.mutateAsync(a.actionId),
              })
            }
            onCorrect={() => {
              let note = '';
              modal.confirm({
                title: '纠正这个动作',
                content: (
                  <div>
                    <p>已发出的消息无法撤回。说明哪里不对，AI 会生成补救建议，并把这条记入评测样本。</p>
                    <Input.TextArea autoSize={{ minRows: 2 }} placeholder="比如：班车信息已经过时，现在只有一班" onChange={(e) => (note = e.target.value)} />
                  </div>
                ),
                okText: '提交纠正',
                cancelText: '返回',
                onOk: () => correct.mutateAsync({ id: a.actionId, note }),
              });
            }}
          />
        ))}
      </div>
    </section>
  );
}
