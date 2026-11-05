import { Button } from 'antd';
import { formatTime, type AiActivity } from '@recruiter/domain';
import { LevelTag } from './Tags';

/** AI 动态：可逆动作 24 小时内可撤销；不可逆动作（已发消息）只能纠正（PRD 6.6） */
export function AiActivityItem({ a, onUndo, onCorrect }: { a: AiActivity; onUndo: () => void; onCorrect: () => void }) {
  const canUndo = a.reversible && !a.undone && (!a.undoUntil || new Date(a.undoUntil) > new Date());
  return (
    <div className="rc-act" data-undone={!!a.undone}>
      <span className="time num">{formatTime(a.at)}</span>
      <span className="text">{a.text}</span>
      <span className="ops">
        <LevelTag level={a.level} />
        <span title={a.reason}>为什么</span>
        {a.undone ? (
          <span>已撤销</span>
        ) : a.corrected ? (
          <span>已标记纠正</span>
        ) : canUndo ? (
          <Button type="link" size="small" style={{ padding: 0, height: 'auto' }} onClick={onUndo}>
            撤销
          </Button>
        ) : (
          <Button type="link" size="small" style={{ padding: 0, height: 'auto' }} onClick={onCorrect}>
            纠正
          </Button>
        )}
      </span>
    </div>
  );
}
