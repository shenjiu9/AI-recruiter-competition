import { Tag } from 'antd';
import type { KbEntry, Profile } from '@recruiter/domain';
import { EmptyState } from '@recruiter/ui-kit';

const GROUPS = [
  { type: 'must', title: '必备条件', hint: '不满足即不推进' },
  { type: 'plus', title: '加分项', hint: '带权重' },
  { type: 'redflag', title: '不合适信号', hint: '见到即降分或转人工' },
  { type: 'must_ask', title: '必问项', hint: 'AI 沟通中必须问到' },
] as const;

const DISCLOSURE = { proactive: '可主动说', on_ask: '被问到可说', internal: '不可说（仅内部参考）', human: '转人工' } as const;

export function ProfilePanel({ profile }: { profile: Profile }) {
  if (!profile.items.length) return <EmptyState title="还没有画像" why="岗位刚生成时 AI 会起草画像，用人经理确认后才能发布。" />;
  return (
    <div>
      <p className="muted" style={{ marginTop: 0 }}>
        画像 v{profile.version}{profile.confirmedBy ? `，${profile.confirmedBy}已确认` : '，等待用人经理确认'}。修改必备条件会生成新版本，已评估的人按旧版本保留结论。
      </p>
      {GROUPS.map((g) => {
        const items = profile.items.filter((i) => i.type === g.type);
        if (!items.length) return null;
        return (
          <section key={g.type} style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 14, fontWeight: 500, margin: '0 0 6px' }}>
              {g.title}
              <span className="muted" style={{ fontWeight: 400, fontSize: 12, marginLeft: 8 }}>{g.hint}</span>
            </h3>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {items.map((i) => (
                <li key={i.id} style={{ padding: '2px 0' }}>
                  {i.text}
                  {'weight' in i && i.weight && <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>权重{i.weight}</span>}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

export function KbPanel({ entries }: { entries: KbEntry[] }) {
  return (
    <div>
      <p className="muted" style={{ marginTop: 0 }}>知识库是 AI 回答候选人问题的唯一依据。这里没有的内容，AI 会回答“确认后回复您”并转给你。</p>
      {entries.map((e) => (
        <div key={e.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--rc-line)' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span className="num muted" style={{ fontSize: 12, width: 48 }}>{e.id}</span>
            <strong style={{ fontWeight: 500 }}>{e.title}</strong>
            <Tag bordered={false}>{e.scope === 'company' ? '公司通用' : '本岗位'}</Tag>
            <Tag bordered={false} color={e.disclosure === 'internal' ? 'warning' : undefined}>{DISCLOSURE[e.disclosure]}</Tag>
          </div>
          <div style={{ marginLeft: 56, color: 'var(--rc-ink-2)' }}>{e.content}</div>
        </div>
      ))}
    </div>
  );
}
