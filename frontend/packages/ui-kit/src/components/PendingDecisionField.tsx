import { Button, Space } from 'antd';
import type { PendingDecision } from '@recruiter/domain';

/** 待决定项：AI 无法确定或发现冲突时，在字段下方直接给选项（RQ-02） */
export function PendingDecisionField({ pending, onChoose }: { pending: PendingDecision; onChoose: (option: string) => void }) {
  return (
    <div className="rc-pending" role="group" aria-label={`待决定：${pending.question}`}>
      <div className="q">{pending.question}</div>
      <Space wrap>
        {pending.options.map((o) => (
          <Button key={o} size="small" onClick={() => onChoose(o)}>
            {o}
          </Button>
        ))}
      </Space>
    </div>
  );
}
