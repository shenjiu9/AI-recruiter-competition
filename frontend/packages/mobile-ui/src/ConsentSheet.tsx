import { Button, Checkbox } from 'antd-mobile';
import { useState, type CSSProperties } from 'react';

/** 候选人授权：说明 AI 身份、AI 会做什么、数据怎么用；未授权不做 AI 评估（PRD 20.4） */
export function ConsentSheet({ companyName, onAgree, onDecline }: { companyName: string; onAgree: () => Promise<void>; onDecline: () => void }) {
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <div className="rm-card">
      <h2>开始之前，请确认授权</h2>
      <div className="rm-sub" style={{ lineHeight: 1.7 }}>
        <p>接下来和您沟通的是{companyName}的 AI 招聘助手。它会：</p>
        <ul style={{ paddingLeft: 20, margin: '4px 0 12px' }}>
          <li>回答您关于岗位的问题，信息来自公司确认过的资料；</li>
          <li>了解您的期望和可到岗时间，并参考您的简历做初步评估；</li>
          <li>帮您安排面试时间。</li>
        </ul>
        <p>是否录用由招聘负责人决定，AI 不会做最终决定。您随时可以点“转人工”联系招聘顾问，也可以撤回授权或申请删除您的信息。</p>
      </div>
      <Checkbox checked={checked} onChange={setChecked} style={{ margin: '12px 0', '--icon-size': '20px' } as CSSProperties}>
        我已阅读并同意《候选人个人信息处理说明》
      </Checkbox>
      <Button
        block
        color="primary"
        size="large"
        disabled={!checked}
        loading={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onAgree();
          } finally {
            setBusy(false);
          }
        }}
      >
        同意并开始
      </Button>
      <Button block fill="none" size="large" style={{ marginTop: 8 }} onClick={onDecline}>
        不同意，改为人工沟通
      </Button>
    </div>
  );
}
