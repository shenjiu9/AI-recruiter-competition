import { CheckOutlined, CloseOutlined, QuestionOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { CONCLUSION_LABEL, formatDateTime, type Evaluation, type EvaluationItem, type EvidenceRef } from '@recruiter/domain';
import { ConfidenceTag, EmptyState, EvidenceChip } from '@recruiter/ui-kit';

const GROUPS: { type: EvaluationItem['type']; title: string }[] = [
  { type: 'must', title: '必备条件' },
  { type: 'plus', title: '加分项' },
  { type: 'redflag', title: '不合适信号' },
];

function VerdictMark({ item }: { item: EvaluationItem }) {
  // 不合适信号：not_meet 表示未命中（好事）
  const good = item.type === 'redflag' ? item.verdict === 'not_meet' : item.verdict === 'meet';
  if (item.verdict === 'unknown') return <span style={{ color: 'var(--rc-warn)' }} aria-label="待确认"><QuestionOutlined /></span>;
  return good ? (
    <span style={{ color: 'var(--rc-ok)' }} aria-label={item.type === 'redflag' ? '未命中' : '满足'}><CheckOutlined /></span>
  ) : (
    <span style={{ color: 'var(--rc-bad)' }} aria-label={item.type === 'redflag' ? '命中' : '不满足'}><CloseOutlined /></span>
  );
}

/** AI 评估表：逐条对照画像，证据点击后在右侧简历中定位高亮（PRD 9.3、17.10） */
export function EvaluationPanel({ ev, activeRefs, onEvidence, onAsk }: { ev: Evaluation | null | undefined; activeRefs: string[]; onEvidence: (e: EvidenceRef) => void; onAsk: (q: string) => void }) {
  if (!ev) return <EmptyState title="还没有 AI 评估" why="候选人授权并补齐简历和必问项后，AI 会按岗位画像出评估表。" />;
  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 16px', alignItems: 'center', padding: '12px 16px', background: 'var(--rc-surface-2)', borderRadius: 4 }}>
        <span className="rc-tag rc-ai">AI 建议</span>
        <strong style={{ fontWeight: 500 }}>{CONCLUSION_LABEL[ev.conclusion]}</strong>
        <ConfidenceTag value={ev.confidence} reasons={ev.lowReasons} />
        <span className="muted">匹配分 <span className="num" style={{ color: 'var(--rc-ink)' }}>{ev.score}</span></span>
        <span className="muted" style={{ fontSize: 12, marginLeft: 'auto' }}>画像 v{ev.profileVersion}，{formatDateTime(ev.at)}</span>
        {ev.lowReasons.length > 0 && <span style={{ flexBasis: '100%', fontSize: 12, color: 'var(--rc-bad)' }}>把握偏低：{ev.lowReasons.join('；')}</span>}
      </div>
      {GROUPS.map((g) => {
        const items = ev.items.filter((i) => i.type === g.type);
        if (!items.length) return null;
        return (
          <section key={g.type} style={{ marginTop: 16 }}>
            <h3 style={{ fontSize: 14, fontWeight: 500, margin: '0 0 4px', color: 'var(--rc-ink-2)' }}>{g.title}</h3>
            {items.map((i) => (
              <div key={i.id} style={{ display: 'grid', gridTemplateColumns: '20px minmax(0,1fr) auto', gap: '2px 10px', padding: '10px 0', borderBottom: '1px solid var(--rc-line)' }}>
                <VerdictMark item={i} />
                <div>
                  {i.text}
                  {i.weight && <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>权重{i.weight}</span>}
                  {i.note && <div className="muted" style={{ fontSize: 12 }}>{i.note}</div>}
                  {i.verdict === 'unknown' && i.question && (
                    <div style={{ marginTop: 6, fontSize: 12 }}>
                      <span style={{ color: 'var(--rc-warn)' }}>待确认。</span>
                      <Button type="link" size="small" style={{ padding: 0, height: 'auto' }} onClick={() => onAsk(i.question!)}>
                        让 AI 补问：{i.question}
                      </Button>
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {i.evidence.map((e) => (
                    <EvidenceChip key={e.ref} ev={e} pressed={activeRefs.includes(e.ref)} onClick={() => onEvidence(e)} />
                  ))}
                </div>
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}
