import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  useApi,
  useReliableWrite,
  toAppError,
  type LiveInterview,
  type InterviewCommand,
} from '@recruiter/api-client';

const STATUS: Record<string, string> = {
  needs_configuration: '正在准备',
  waiting: '等待 HR 提供时段',
  offered: '请选择时间',
  scheduled: '已确定',
  awaiting_feedback: '面试已结束',
  completed: '面试已结束',
  cancelled: '本场已取消',
  no_show: '请联系 HR 核对参加情况',
};
export function CandidateInterviews({ token }: { token: string }) {
  const api = useApi();
  const query = useQuery({
    queryKey: ['candidate-interviews'],
    queryFn: () => api.candidateInterviews(token),
    refetchInterval: 5000,
    retry: false,
  });
  return (
    <section className="rm-card">
      <h2>我的面试安排</h2>
      {query.isError ? (
        <p role="alert">{toAppError(query.error).message}</p>
      ) : query.data?.length ? (
        query.data.map((iv) => (
          <CandidateInterview key={iv.id} iv={iv} token={token} refresh={query.refetch} />
        ))
      ) : (
        <p>暂无面试安排。</p>
      )}
    </section>
  );
}
function CandidateInterview({
  iv,
  token,
  refresh,
}: {
  iv: LiveInterview;
  token: string;
  refresh: () => Promise<unknown>;
}) {
  const api = useApi();
  const [reason, setReason] = useState('');
  const [recording, setRecording] = useState(false);
  const op = useReliableWrite<InterviewCommand, LiveInterview>(
    (body, opts) => api.candidateInterviewCommand(token, iv.id, body, opts),
    () => {
      void refresh();
    },
  );
  return (
    <article style={{ borderTop: '1px solid #ddd', marginTop: 16, paddingTop: 12 }}>
      <h3>
        {iv.position_name} · 第 {iv.round_no} 轮 {iv.round_name}
      </h3>
      <p>{STATUS[iv.status]}</p>
      {iv.start && (
        <p>
          面试时间：{new Date(iv.start).toLocaleString()} — {new Date(iv.end!).toLocaleTimeString()}
        </p>
      )}
      {iv.location && <p>地址或安排说明：{iv.location}</p>}
      {iv.meeting_url && (
        <p>
          <a href={iv.meeting_url} target="_blank" rel="noreferrer">
            进入面试会议
          </a>
        </p>
      )}
      <fieldset disabled={op.locked} style={{ border: 0, padding: 0 }}>
        {iv.format === 'video' && iv.status === 'offered' && (
          <label>
            <input
              type="checkbox"
              checked={recording}
              onChange={(e) => setRecording(e.target.checked)}
            />
            同意本场面试录制用于招聘评估（可不勾选；当前未启用录制）
          </label>
        )}
        {iv.slots.map((s) => (
          <button
            key={s.id}
            style={{ display: 'block', marginBlock: 10, padding: 10, width: '100%' }}
            onClick={() =>
              void op.submit({
                action: 'book',
                expected_version: iv.version,
                slot_id: s.id,
                recording_consent: recording,
              })
            }
          >
            选择 {new Date(s.start).toLocaleString()}
          </button>
        ))}
        {iv.status === 'offered' && (
          <p>时段占位有效期 24 小时，逾期请联系 HR。时间按您的设备时区显示。</p>
        )}
        {['scheduled', 'offered'].includes(iv.status) && (
          <>
            <label>
              改期说明
              <textarea
                aria-label="改期说明"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={2000}
                style={{ width: '100%', boxSizing: 'border-box', padding: 10, fontSize: 16 }}
              />
            </label>
            <button
              disabled={!reason.trim()}
              onClick={() =>
                void op.submit({
                  action: 'request_reschedule',
                  expected_version: iv.version,
                  reason,
                })
              }
            >
              申请调整面试时间
            </button>
            <p>
              距开始至少 2 小时且前两次改期可释放原时段，随后由 HR
              提供新时段；临近开始或第三次起保留原安排并转 HR 协调。
            </p>
          </>
        )}
      </fieldset>
      {iv.requests.map((r, n) => (
        <p key={n}>
          改期请求：{r.reason} · {r.status === 'pending' ? '待 HR 处理' : '已处理'}
        </p>
      ))}
      {op.error && <p role="alert">{op.error}</p>}
      {op.retry && <button onClick={op.retryAction}>重试本次操作</button>}
      {op.conflict && (
        <button
          onClick={async () => {
            await refresh();
            op.refreshed();
          }}
        >
          刷新可选时段
        </button>
      )}
    </article>
  );
}
