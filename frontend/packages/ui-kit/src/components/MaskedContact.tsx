import { App } from 'antd';
import { useState } from 'react';

/** 脱敏联系方式；查看完整值需二次确认并记审计（PRD 3.4、20.5） */
export function MaskedContact({ masked, onReveal, canReveal = true }: { masked: string; onReveal: () => Promise<string>; canReveal?: boolean }) {
  const { modal, message } = App.useApp();
  const [full, setFull] = useState<string | null>(null);
  const reveal = () =>
    modal.confirm({
      title: '查看完整联系方式？',
      content: '该操作会记录审计。单人每天查看超过 200 次时会被临时限制。',
      okText: '查看',
      cancelText: '返回',
      onOk: async () => {
        try {
          setFull(await onReveal());
        } catch {
          message.error('没能获取联系方式。请稍后重试，或联系招聘负责人。');
        }
      },
    });
  return (
    <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
      <span className="num">{full ?? masked}</span>
      {!full && canReveal && (
        <button type="button" onClick={reveal} style={{ border: 0, background: 'none', padding: 0, color: 'var(--rc-brand)', cursor: 'pointer', fontSize: 12 }}>
          查看完整
        </button>
      )}
    </span>
  );
}
