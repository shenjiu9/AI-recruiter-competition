import { Button, TextArea } from 'antd-mobile';
import { useState } from 'react';

/** 底部输入栏：触控目标 ≥ 44px，适配安全区 */
export function Composer({ onSend, disabled }: { onSend: (t: string) => Promise<void>; disabled?: boolean }) {
  const [text, setText] = useState('');
  return (
    <div style={{ position: 'sticky', bottom: 0, display: 'flex', gap: 8, alignItems: 'flex-end', padding: '8px 12px calc(8px + env(safe-area-inset-bottom))', background: 'var(--adm-color-background)', borderTop: '1px solid var(--adm-color-border)' }}>
      <div style={{ flex: 1, padding: '8px 10px', borderRadius: 8, background: 'var(--rm-paper)' }}>
        <TextArea aria-label="输入消息" placeholder="输入您的问题或回复" value={text} onChange={setText} autoSize={{ minRows: 1, maxRows: 4 }} disabled={disabled} />
      </div>
      <Button
        color="primary"
        style={{ minHeight: 44, minWidth: 64 }}
        disabled={!text.trim() || disabled}
        onClick={async () => {
          const t = text.trim();
          setText('');
          await onSend(t);
        }}
      >
        发送
      </Button>
    </div>
  );
}
