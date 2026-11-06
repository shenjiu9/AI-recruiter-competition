import { Button, Dialog, NavBar, Result, Skeleton } from 'antd-mobile';
import { useState } from 'react';
import { ChatView, ConsentSheet, SlotPicker } from '@recruiter/mobile-ui';
import { track, usePageView } from '@recruiter/telemetry';
import { Composer, usePortal } from '../features/portal';

const token = new URLSearchParams(location.search).get('t') ?? 'demo';

/** EX-01 / EX-02：AI 身份说明 → 授权 → 会话；在会话里用卡片选面试时间 */
export function PortalPage() {
  usePageView('EX-01');
  const p = usePortal(token);
  const [declined, setDeclined] = useState(false);
  const [slotDone, setSlotDone] = useState(false);
  const s = p.session.data;

  if (p.session.isLoading || !s)
    return (
      <div className="rm-card">
        <Skeleton.Paragraph lineCount={5} animated />
      </div>
    );

  const header = (
    <NavBar
      back={null}
      right={
        s.consent === 'granted' ? (
          <Button
            size="small"
            fill="outline"
            onClick={() => {
              void Dialog.confirm({
                content: '转给招聘顾问后，AI 不再自动回复，工作时间 2 小时内会有人联系您。',
                confirmText: '转人工',
                cancelText: '返回',
                onConfirm: async () => {
                  await p.askHuman.mutateAsync();
                },
              });
            }}
          >
            转人工
          </Button>
        ) : null
      }
    >
      <div style={{ lineHeight: 1.3 }}>
        <div style={{ fontSize: 16, fontWeight: 500 }}>{s.companyName} AI 招聘助手</div>
        <div style={{ fontSize: 12, color: 'var(--rm-ink-3)' }}>{s.positionName}</div>
      </div>
    </NavBar>
  );

  if (declined)
    return (
      <main>
        {header}
        <Result
          status="info"
          title="已为您转为人工沟通"
          description="招聘顾问会在工作时间 2 小时内通过短信或电话联系您。您的信息不会用于 AI 评估。"
        />
      </main>
    );

  if (s.consent !== 'granted')
    return (
      <main>
        {header}
        <div className="rm-card">
          <h2>{s.candidateName}您好</h2>
          <div className="rm-sub">
            我是{s.companyName}的 AI 招聘助手，负责和您沟通{s.positionName}岗位的进展。
          </div>
        </div>
        <ConsentSheet
          companyName={s.companyName}
          onAgree={async () => {
            await p.consent.mutateAsync(true);
            track('ex_consent', { granted: true });
          }}
          onDecline={() => {
            setDeclined(true);
            track('ex_consent', { granted: false });
          }}
        />
      </main>
    );

  return (
    <main style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {header}
      <div
        role="status"
        style={{
          padding: '8px 16px',
          fontSize: 13,
          color: 'var(--adm-color-text-secondary)',
          background: 'var(--rm-surface-2)',
        }}
      >
        进度：{s.progress}
      </div>
      <div style={{ flex: 1 }}>
        <ChatView
          messages={p.messages.data ?? []}
          footer={
            !slotDone && p.slots.data?.length ? (
              <SlotPicker
                slots={p.slots.data}
                onPick={async (id) => {
                  await p.pick.mutateAsync(id);
                  setSlotDone(true);
                  track('ex_slot_select', { attempts: 1 });
                }}
              />
            ) : null
          }
        />
      </div>
      <Composer onSend={async (t) => void (await p.send.mutateAsync(t))} />
    </main>
  );
}
