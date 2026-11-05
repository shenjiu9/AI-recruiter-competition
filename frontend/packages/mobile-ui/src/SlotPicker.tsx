import { Button } from 'antd-mobile';
import { useState } from 'react';
import { formatSlot, type Slot } from '@recruiter/domain';

/** 在会话中以卡片形式选择面试时段；触控目标 ≥ 48px */
export function SlotPicker({ slots, onPick, disabled }: { slots: Slot[]; onPick: (id: string) => Promise<void>; disabled?: boolean }) {
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="rm-msg ai" style={{ maxWidth: '92%' }}>
      <div className="rm-bubble">
        <div>请选择复试时间（约 60 分钟）：</div>
        <div className="rm-slots" role="radiogroup" aria-label="可选面试时间">
          {slots.map((s) => (
            <button key={s.id} type="button" className="rm-slot" role="radio" aria-checked={picked === s.id} aria-pressed={picked === s.id} disabled={disabled} onClick={() => setPicked(s.id)}>
              {formatSlot(s.start, s.end)}
            </button>
          ))}
        </div>
        <Button
          block
          color="primary"
          style={{ marginTop: 12 }}
          disabled={!picked || disabled}
          loading={busy}
          onClick={async () => {
            if (!picked) return;
            setBusy(true);
            try {
              await onPick(picked);
            } finally {
              setBusy(false);
            }
          }}
        >
          确认这个时间
        </Button>
        <div style={{ marginTop: 8, fontSize: 13, color: 'var(--rm-ink-3)' }}>都不方便？直接回复您可以的时间，比如“下周二下午”。</div>
      </div>
    </div>
  );
}
