import { Button, Space, Tooltip } from 'antd';
import { useApi, useIdempotencyKey } from '@recruiter/api-client';
import type { Candidate } from '@recruiter/domain';
import { usePermission } from '@recruiter/permissions';
import { MaskedContact } from '@recruiter/ui-kit';
import { useWrite } from '../../../shared/useWrite';
import { qk } from '@recruiter/domain';

const Field = ({ label, value }: { label: string; value: string }) => (
  <span>
    <span className="muted" style={{ marginRight: 6 }}>{label}</span>
    {value}
  </span>
);

/** 头部：姓名 + 标签值字段（不用中点拼接）+ 脱敏联系方式 + 关键候选人 */
export function CandidateHeader({ c }: { c: Candidate }) {
  const api = useApi();
  const idem = useIdempotencyKey();
  const canReveal = usePermission('candidate.reveal_contact');
  const canKey = usePermission('candidate.mark_key');
  const setKey = useWrite((v: boolean, opts) => api.setKey(c.id, v, c.version, opts), {
    invalidate: [qk.candidate.detail(c.id)],
    success: (r) => (r.isKey ? '已标记为关键候选人，对外动作最高 L2' : '已取消关键候选人'),
  });
  return (
    <header style={{ display: 'flex', gap: 24, alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: 16 }}>
      <div style={{ minWidth: 0 }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 12 }}>
          {c.name}
          {c.isKey && <span className="rc-tag" style={{ background: 'var(--rc-brand-soft)', color: 'var(--rc-brand)' }}>关键候选人</span>}
          {c.consent === 'none' && <Tooltip title="未授权前不做 AI 评估"><span className="rc-tag">未授权</span></Tooltip>}
        </h1>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 20px', marginTop: 6 }}>
          <Field label="当前" value={`${c.currentTitle}，${c.currentCompany}`} />
          <Field label="城市" value={c.city} />
          <Field label="经验" value={`${c.years} 年`} />
          <Field label="学历" value={c.education} />
        </div>
      </div>
      <Space style={{ marginLeft: 'auto' }} wrap>
        <span>
          <span className="muted" style={{ marginRight: 6 }}>联系方式</span>
          <MaskedContact
            masked={c.phoneMasked}
            canReveal={canReveal}
            onReveal={async () => {
              const r = await api.revealContact(c.id, { idempotencyKey: idem.key() });
              idem.reset();
              return `${r.phone}  ${r.email}`;
            }}
          />
        </span>
        {canKey && (
          <Button onClick={() => setKey.mutate(!c.isKey)} loading={setKey.isPending}>
            {c.isKey ? '取消关键候选人' : '标记关键候选人'}
          </Button>
        )}
      </Space>
    </header>
  );
}
