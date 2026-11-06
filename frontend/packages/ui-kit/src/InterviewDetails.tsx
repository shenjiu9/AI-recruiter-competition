import { useState } from 'react';
import {
  useApi,
  useReliableWrite,
  type InterviewCommand,
  type LiveInterview,
} from '@recruiter/api-client';

export const INTERVIEW_STATUS: Record<string, string> = {
  needs_configuration: '待配置流程',
  waiting: '待约',
  offered: '约面中',
  scheduled: '已确定',
  awaiting_feedback: '待面评',
  completed: '已完成',
  cancelled: '已取消',
  no_show: '候选人缺席',
};
export const INTERVIEW_RESULT: Record<string, string> = {
  pass: '通过',
  needs_hr_decision: '待 HR 决策',
};
const RECOMMEND: Record<string, string> = {
  strong_yes: '强烈推荐',
  yes: '推荐',
  hold: '待定',
  no: '不推荐',
};
const FORMAT: Record<string, string> = {
  phone: '电话',
  onsite: '现场',
  video: '视频',
  ai: 'AI 初面',
};
const fieldStyle = {
  width: '100%',
  boxSizing: 'border-box' as const,
  padding: 10,
  fontSize: 16,
  marginBlock: 6,
};
const blockStyle = {
  background: '#fff',
  border: '1px solid #dfe5ec',
  borderRadius: 10,
  padding: 16,
  marginBlock: 16,
};

export function InterviewDetails({
  interview: iv,
  onUpdated,
  refresh,
}: {
  interview: LiveInterview;
  onUpdated: (iv: LiveInterview) => void;
  refresh: () => Promise<unknown>;
}) {
  const api = useApi();
  const [start, setStart] = useState('');
  const [location, setLocation] = useState(iv.location);
  const [meeting, setMeeting] = useState(iv.meeting_url);
  const [reason, setReason] = useState('');
  const [verified, setVerified] = useState(false);
  const [scores, setScores] = useState<Record<string, number>>(iv.my_feedback?.scores ?? {});
  const [recommendation, setRecommendation] = useState<InterviewCommand['recommendation']>(
    (iv.my_feedback?.recommendation as InterviewCommand['recommendation']) ?? '',
  );
  const [strengths, setStrengths] = useState(iv.my_feedback?.strengths ?? '');
  const [concerns, setConcerns] = useState(iv.my_feedback?.concerns ?? '');
  const [focus, setFocus] = useState(iv.my_feedback?.next_focus ?? '');
  const [answers, setAnswers] = useState<Record<string, string>>(iv.my_feedback?.answers ?? {});
  const [checked, setChecked] = useState(false);
  const [recused, setRecused] = useState(false);
  const op = useReliableWrite<InterviewCommand, LiveInterview>(
    (body, opts) => api.interviewCommand(iv.id, body, opts),
    onUpdated,
  );
  const run = (action: InterviewCommand['action'], extra: Partial<InterviewCommand> = {}) =>
    void op.submit({ action, expected_version: iv.version, reason, ...extra });
  const criteria = [
    ...new Set(
      iv.spec?.criteria
        .split('\n')
        .map((x) => x.trim())
        .filter(Boolean) ?? [],
    ),
  ];
  const questions = [
    ...new Set(
      iv.must_ask
        ?.split('\n')
        .map((x) => x.trim())
        .filter(Boolean) ?? [],
    ),
  ];
  return (
    <article aria-label="面试详情" style={{ maxWidth: 900, marginInline: 'auto' }}>
      <h2>
        {iv.candidate_name} · 第 {iv.round_no} 轮 {iv.round_name}
      </h2>
      <p>
        {iv.position_name} · {FORMAT[iv.format] ?? '待配置'} · {INTERVIEW_STATUS[iv.status]}
        {iv.result ? ` · ${INTERVIEW_RESULT[iv.result]}` : ''}
      </p>
      <p>
        {iv.start
          ? `${new Date(iv.start).toLocaleString()} — ${new Date(iv.end!).toLocaleTimeString()}`
          : '尚未确定时间'}{' '}
        · 流程版本 {iv.plan_version}
      </p>
      <p>面试官：{iv.interviewers?.map((u) => u.name).join('、') || '待配置'}</p>
      {iv.location && <p>地点 / 指引：{iv.location}</p>}
      {iv.meeting_url && (
        <p>
          <a href={iv.meeting_url} target="_blank" rel="noreferrer">
            打开已核实的会议链接
          </a>
        </p>
      )}
      <p>
        外部日历 / 会议：
        {iv.integration_state === 'manual' || iv.integration_state === 'not_requested'
          ? '当前由 HR 人工核实；本地预约不会自动创建会议或外部日程'
          : iv.integration_state === 'synced'
            ? '已同步'
            : iv.integration_state === 'cleanup'
              ? '失败清理中'
              : iv.integration_state.startsWith('uncertain_')
                ? '同步结果待核实，请使用原请求重试后再调整安排'
                : iv.integration_state === 'failed'
                  ? '同步失败，待人工处理'
                  : '等待同步'}
        。当前未启用录制。
      </p>
      <section style={blockStyle}>
        <h3>面试准备</h3>
        <p>{iv.profile?.skills || '暂无技能摘要'}</p>
        <p style={{ whiteSpace: 'pre-wrap' }}>{iv.profile?.experience}</p>
        <p>评价维度：{criteria.join('、') || '待配置'}</p>
        <p>评分标准：1 分明显不足，2 分部分满足，3 分达到要求，4 分表现良好，5 分显著超出要求。</p>
        {iv.must_ask && <p style={{ whiteSpace: 'pre-wrap' }}>必问题：{iv.must_ask}</p>}
        {iv.previous_rounds?.map((r) => (
          <details key={r.round_no}>
            <summary>
              前轮 {r.round_no}：{INTERVIEW_RESULT[r.result ?? ''] ?? '尚无结论'}
            </summary>
            {r.feedback ? (
              Object.values(r.feedback).map((f) => (
                <p key={f.author}>
                  {RECOMMEND[f.recommendation]} ·{' '}
                  {Object.entries(f.scores)
                    .map(([k, v]) => `${k} ${v}分`)
                    .join('、')}{' '}
                  · {f.strengths} · {f.concerns}
                </p>
              ))
            ) : (
              <p>提交本轮面评后可查看前轮评分和理由。</p>
            )}
          </details>
        ))}
      </section>
      {iv.can_edit && (
        <section style={blockStyle}>
          <h3>HR 排期与状态操作</h3>
          <fieldset disabled={op.locked} style={{ border: 0, padding: 0 }}>
            {iv.status === 'needs_configuration' && (
              <button onClick={() => run('configure')}>使用岗位最新流程</button>
            )}
            {['waiting', 'offered'].includes(iv.status) && (
              <>
                <label>
                  面试地址或电话安排说明
                  <input
                    style={fieldStyle}
                    aria-label="面试地址或说明"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    maxLength={1000}
                  />
                </label>
                <label>
                  已核实的 HTTPS 会议链接
                  <input
                    style={fieldStyle}
                    aria-label="会议链接"
                    value={meeting}
                    onChange={(e) => setMeeting(e.target.value)}
                    maxLength={1000}
                  />
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={verified}
                    onChange={(e) => setVerified(e.target.checked)}
                  />
                  我已核实外部日历忙闲和面试安排
                </label>
                <br />
                <button
                  disabled={!verified}
                  onClick={() => run('offer', { verified, location, meeting_url: meeting })}
                >
                  生成候选人可选时段
                </button>
                <label>
                  手动安排时间（本机时区）
                  <input
                    style={fieldStyle}
                    aria-label="手动安排时间"
                    type="datetime-local"
                    value={start}
                    onChange={(e) => setStart(e.target.value)}
                  />
                </label>
                <button
                  disabled={!verified || !start}
                  onClick={() =>
                    run('book', {
                      verified,
                      start: new Date(start).toISOString(),
                      location,
                      meeting_url: meeting,
                    })
                  }
                >
                  确认手动安排
                </button>
              </>
            )}
            {iv.slots.map((s) => (
              <p key={s.id}>
                可选：{new Date(s.start).toLocaleString()}（占位至{' '}
                {new Date(s.expires_at).toLocaleString()}）
              </p>
            ))}
            <label>
              操作原因 / 实际面试情况
              <textarea
                aria-label="面试操作原因"
                style={fieldStyle}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={2000}
              />
            </label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {['scheduled', 'offered', 'no_show'].includes(iv.status) && (
                <button disabled={!reason.trim()} onClick={() => run('reschedule')}>
                  重新协调时间
                </button>
              )}
              {iv.status === 'scheduled' && (
                <>
                  <button disabled={!reason.trim()} onClick={() => run('complete')}>
                    确认面试已结束
                  </button>
                  <button disabled={!reason.trim()} onClick={() => run('no_show')}>
                    确认候选人缺席
                  </button>
                </>
              )}
              {!['completed', 'cancelled'].includes(iv.status) && (
                <button disabled={!reason.trim()} onClick={() => run('cancel')}>
                  取消本场面试
                </button>
              )}
              {['failed', 'uncertain_meeting', 'uncertain_calendar'].includes(
                iv.integration_state,
              ) && <button onClick={() => run('retry_integration')}>重试外部同步</button>}
            </div>
          </fieldset>
        </section>
      )}
      {iv.can_feedback && (
        <section style={blockStyle}>
          <h3>本人面评</h3>
          <fieldset disabled={op.locked} style={{ border: 0, padding: 0 }}>
            {criteria.map((key) => (
              <label key={key} style={{ display: 'block', marginBlock: 10 }}>
                {key}评分{' '}
                <select
                  aria-label={`${key}评分`}
                  value={scores[key] ?? ''}
                  onChange={(e) => setScores({ ...scores, [key]: Number(e.target.value) })}
                >
                  <option value="">请选择</option>
                  {[1, 2, 3, 4, 5].map((v) => (
                    <option key={v} value={v}>
                      {v} 分
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <label>
              面评结论{' '}
              <select
                aria-label="面评结论"
                value={recommendation}
                onChange={(e) =>
                  setRecommendation(e.target.value as InterviewCommand['recommendation'])
                }
              >
                <option value="">由面试官选择</option>
                {Object.entries(RECOMMEND).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: 'block', marginTop: 12 }}>
              优势
              <textarea
                aria-label="面评优势"
                style={fieldStyle}
                value={strengths}
                onChange={(e) => setStrengths(e.target.value)}
                maxLength={4000}
              />
            </label>
            <label>
              顾虑（待定或不推荐时必填）
              <textarea
                aria-label="面评顾虑"
                style={fieldStyle}
                value={concerns}
                onChange={(e) => setConcerns(e.target.value)}
                maxLength={4000}
              />
            </label>
            <label>
              建议下一轮关注
              <textarea
                aria-label="下一轮关注"
                style={fieldStyle}
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                maxLength={2000}
              />
            </label>
            {questions.map((q) => (
              <label key={q}>
                {q}
                <textarea
                  style={fieldStyle}
                  aria-label={`必问题：${q}`}
                  value={answers[q] ?? ''}
                  maxLength={2000}
                  onChange={(e) => setAnswers({ ...answers, [q]: e.target.value })}
                />
              </label>
            ))}
            <label>
              <input
                type="checkbox"
                checked={recused}
                onChange={(e) => setRecused(e.target.checked)}
              />
              本人存在亲属关系等需回避情形
            </label>
            <br />
            <label>
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => setChecked(e.target.checked)}
              />
              我已核对并对内容负责
            </label>
            <br />
            <button
              disabled={
                !checked || recused || !['awaiting_feedback', 'completed'].includes(iv.status)
              }
              onClick={() =>
                run('feedback', {
                  scores,
                  recommendation,
                  strengths,
                  concerns,
                  next_focus: focus,
                  answers,
                  verified: checked,
                  recused,
                })
              }
            >
              {iv.my_feedback ? '保存面评修改' : '提交本人面评'}
            </button>
            <p>
              首次提交后 24
              小时内可修改并留痕；结论已用于后续安排时须先协调。此后仅追加备注。不推荐不会自动淘汰。
            </p>
            {!iv.can_edit && (
              <label>
                改期 / 备注说明
                <textarea
                  aria-label="面试操作原因"
                  style={fieldStyle}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={2000}
                />
              </label>
            )}
            {['scheduled', 'offered'].includes(iv.status) && (
              <button disabled={!reason.trim()} onClick={() => run('request_reschedule')}>
                申请面试改期
              </button>
            )}
            {iv.my_feedback && (
              <button disabled={!reason.trim()} onClick={() => run('remark')}>
                追加面评备注
              </button>
            )}
          </fieldset>
        </section>
      )}
      {op.error && <p role="alert">{op.error}</p>}
      {op.retry && (
        <button disabled={op.busy} onClick={op.retryAction}>
          重试本次操作
        </button>
      )}
      {op.conflict && (
        <button
          onClick={async () => {
            await refresh();
            op.refreshed();
          }}
        >
          刷新面试记录
        </button>
      )}
      <section style={blockStyle}>
        <h3>面评记录</h3>
        {Object.values(iv.feedback ?? {}).map((f) => (
          <article key={f.author}>
            <p>
              {iv.interviewers?.find((u) => u.id === f.author)?.name}：{RECOMMEND[f.recommendation]}
            </p>
            <p>
              {Object.entries(f.scores)
                .map(([k, v]) => `${k} ${v} 分`)
                .join('、')}
            </p>
            <p>{f.strengths}</p>
            <p>{f.concerns}</p>
            {f.remarks?.map((r) => (
              <p key={r.at}>追加备注：{r.text}</p>
            ))}
          </article>
        ))}
        {iv.requests.map((r, i) => (
          <p key={i}>
            改期请求：{r.reason} · {r.status === 'pending' ? '待 HR 处理' : '已处理'}
          </p>
        ))}
        {iv.reminders
          ?.filter((r) => r.kind === 'feedback')
          .map((r) => (
            <p key={r.key}>面评待办：结束后 {r.hours} 小时仍未提交（站内记录）</p>
          ))}
      </section>
    </article>
  );
}
