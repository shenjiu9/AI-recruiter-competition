import { useQuery } from '@tanstack/react-query';
import { Button, Dialog, Skeleton, Toast } from 'antd-mobile';
import { useApi, useIdempotencyKey } from '@recruiter/api-client';
import { CONFIDENCE_LABEL, confidenceBand, qk } from '@recruiter/domain';

/** BZ-02 候选人精简视图：推荐理由（带原文）、风险、面评；联系方式脱敏 */
export function BriefView({ appId, onDone }: { appId: string; onDone: () => void }) {
  const api = useApi();
  const idem = useIdempotencyKey();
  const { data: b, isLoading } = useQuery({
    queryKey: qk.biz.brief(appId),
    queryFn: () => api.candidateBrief(appId),
  });
  if (isLoading || !b)
    return (
      <div className="rm-card">
        <Skeleton.Paragraph lineCount={6} animated />
      </div>
    );
  const band = confidenceBand(b.confidence);
  const decide = async (action: string) => {
    await api.bizAct('b1', action, { idempotencyKey: idem.key() });
    idem.reset();
    Toast.show({
      icon: 'success',
      content: action === '想见' ? '已通知 HR 安排复试' : '已通知 HR',
    });
    onDone();
  };
  return (
    <>
      <section className="rm-card">
        <h2>{b.name}</h2>
        <div className="rm-sub">{b.positionName}</div>
        <div className="rm-sub" style={{ marginTop: 4 }}>
          {b.headline}
        </div>
        <div className="rm-sub" style={{ marginTop: 4 }}>
          联系方式 {b.phoneMasked}（由 HR 联系）
        </div>
        <div
          style={{
            marginTop: 12,
            padding: '10px 12px',
            borderRadius: 8,
            background: 'var(--rm-surface-2)',
          }}
        >
          <span className="rm-tag-ai">AI 建议</span>{' '}
          <strong style={{ fontWeight: 500 }}>{b.recommendation}</strong>
          <span style={{ marginLeft: 8, fontSize: 13 }}>
            {CONFIDENCE_LABEL[band]} {b.confidence.toFixed(2)}
          </span>
        </div>
      </section>
      <section className="rm-card" aria-labelledby="hl">
        <h2 id="hl" style={{ fontSize: 16 }}>
          推荐理由
        </h2>
        {b.highlights.map((h) => (
          <div key={h.ref} style={{ marginTop: 10 }}>
            <div>{h.text}</div>
            <div className="rm-quote">
              <span className="rm-ref">{h.ref}</span>
              {h.quote}
            </div>
          </div>
        ))}
      </section>
      <section className="rm-card" aria-labelledby="rk">
        <h2 id="rk" style={{ fontSize: 16 }}>
          需要留意
        </h2>
        <ul style={{ paddingLeft: 20, margin: '6px 0 0' }}>
          {b.risks.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </section>
      <section className="rm-card" aria-labelledby="fb">
        <h2 id="fb" style={{ fontSize: 16 }}>
          面评
        </h2>
        {b.feedbacks.map((f) => (
          <div key={f.interviewer} style={{ marginTop: 10 }}>
            <div>
              <strong style={{ fontWeight: 500 }}>{f.interviewer}</strong>
              <span className="rm-sub" style={{ marginLeft: 8 }}>
                {f.round}，{f.verdict}
              </span>
            </div>
            <div className="rm-sub">{f.summary}</div>
          </div>
        ))}
      </section>
      <div
        style={{
          position: 'sticky',
          bottom: 0,
          padding: '12px 16px calc(12px + env(safe-area-inset-bottom))',
          background: 'var(--adm-color-background)',
          borderTop: '1px solid var(--adm-color-border)',
          display: 'flex',
          gap: 8,
        }}
      >
        <Button
          size="large"
          style={{ flex: 1 }}
          onClick={() => {
            void Dialog.confirm({
              content: `确定${b.name}不合适？HR 会按流程处理并通知候选人。`,
              confirmText: '不合适',
              cancelText: '返回',
              onConfirm: () => decide('不合适'),
            });
          }}
        >
          不合适
        </Button>
        <Button size="large" color="primary" style={{ flex: 2 }} onClick={() => decide('想见')}>
          想见，安排复试
        </Button>
      </div>
    </>
  );
}
