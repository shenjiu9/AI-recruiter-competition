import { useState } from 'react';
import { Alert, Button, Checkbox, Input, Space, Table, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import {
  useApi,
  toAppError,
  type LivePosition,
  type PositionCommand,
  type KnowledgeEntry,
  type PositionInterviewRound,
} from '@recruiter/api-client';
import { DirectoryPersonPicker } from '@recruiter/ui-kit/directory-person-picker';
import { Link } from 'react-router-dom';

const DISCLOSURE = {
  proactive: '可主动说',
  asked: '被问到可说',
  internal: '仅内部参考',
  handoff: '转人工',
};
const JD_STATUS = { draft: '待审批', approved: '已批准', rejected: '已驳回' };
type Action = PositionCommand['action'];

export function ExtendedPositionForm({
  pos,
  body,
  set,
  locked,
}: {
  pos: LivePosition;
  body: PositionCommand;
  set: (patch: Partial<PositionCommand>) => void;
  locked: boolean;
}) {
  const action = body.action;
  const rounds = body.rounds ?? [];
  const updateRound = (index: number, patch: Partial<PositionInterviewRound>) =>
    set({ rounds: rounds.map((r, i) => (i === index ? { ...r, ...patch } : r)) });
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {action === 'save_profile' &&
        (body.plus ?? '')
          .split('\n')
          .filter((s) => s.trim())
          .map((line, i) => (
            <label key={i}>
              加分项权重：{line}
              <select
                aria-label={`第 ${i + 1} 项权重`}
                value={body.plus_weights?.[i] ?? 'medium'}
                onChange={(e) => {
                  const weights = [...(body.plus_weights ?? [])];
                  weights[i] = e.target.value as 'high' | 'medium' | 'low';
                  set({ plus_weights: weights });
                }}
              >
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </label>
          ))}
      {action === 'save_jd' && (
        <label>
          JD 正文
          <Input.TextArea
            aria-label="JD 正文"
            value={body.jd}
            rows={8}
            maxLength={4000}
            onChange={(e) => set({ jd: e.target.value })}
          />
        </label>
      )}
      {action === 'configure_publish' && (
        <Checkbox
          disabled={locked}
          checked={body.jd_approval_required}
          onChange={(e) => set({ jd_approval_required: e.target.checked })}
        >
          发布与更新 JD 需招聘负责人审批
        </Checkbox>
      )}
      {['approve_jd', 'apply_jd'].includes(action) && (
        <>
          <p>处理第 {pos.jd.version} 版 JD。</p>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{pos.jd.content}</pre>
        </>
      )}
      {['reject_jd', 'reject_close'].includes(action) && (
        <label>
          驳回原因
          <Input.TextArea
            aria-label="驳回原因"
            value={body.reason}
            maxLength={500}
            onChange={(e) => set({ reason: e.target.value })}
          />
        </label>
      )}
      {action === 'confirm_close' && (
        <p>确认关闭原因：{pos.closeRequest?.reason}。确认后岗位只读，并释放尚未使用的编制预占。</p>
      )}
      {action === 'save_kb' && (
        <>
          <label>
            知识内容
            <Input.TextArea
              aria-label="知识内容"
              value={body.content}
              rows={4}
              maxLength={4000}
              onChange={(e) => set({ content: e.target.value })}
            />
          </label>
          <label>
            知识来源
            <Input
              aria-label="知识来源"
              value={body.source}
              maxLength={300}
              onChange={(e) => set({ source: e.target.value })}
            />
          </label>
          <label>
            披露级别{' '}
            <select
              aria-label="披露级别"
              value={body.disclosure ?? 'internal'}
              onChange={(e) => set({ disclosure: e.target.value as KnowledgeEntry['disclosure'] })}
            >
              {Object.entries(DISCLOSURE).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <p>修订后生成新编号，旧编号立即失效。保密岗位的知识不会进入对外答复预览。</p>
        </>
      )}
      {action === 'retire_kb' && <p>下线后该条知识不能再被用于对外答复。</p>}
      {action === 'share' && (
        <>
          <p>最多 5 位共享 HR，可编辑岗位；移除后撤销该项共享授权。</p>
          <DirectoryPersonPicker
            id="shared-hr"
            label="共享 HR"
            dept={pos.dept}
            value={body.shared_ids ?? []}
            multiple
            disabled={locked}
            onChange={(ids) => set({ shared_ids: ids })}
          />
        </>
      )}
      {action === 'comment' && (
        <>
          <label>
            留言内容
            <Input.TextArea
              aria-label="留言内容"
              value={body.content}
              rows={4}
              maxLength={4000}
              onChange={(e) => set({ content: e.target.value })}
            />
          </label>
          <Checkbox.Group
            disabled={locked}
            value={body.mentions ?? []}
            options={[
              { label: pos.hiringManager, value: pos.managerId },
              ...(pos.ownerId ? [{ label: pos.ownerHr, value: pos.ownerId }] : []),
              ...pos.sharedMembers.map((m) => ({ label: m.name, value: m.id })),
            ]}
            onChange={(ids) => set({ mentions: ids as string[] })}
          />
          <p>勾选要提及的协作成员，留言保存在本岗位。</p>
        </>
      )}
      {action === 'save_interview_plan' && (
        <>
          <p>保存为新的流程版本，后续面试使用此版本；历史版本保留。</p>
          {rounds.map((r, i) => (
            <div key={i} style={{ border: '1px solid #ddd', padding: 12, display: 'grid', gap: 8 }}>
              <label>
                第 {i + 1} 轮名称
                <Input
                  aria-label={`第 ${i + 1} 轮名称`}
                  value={r.name}
                  maxLength={100}
                  onChange={(e) => updateRound(i, { name: e.target.value })}
                />
              </label>
              <label>
                形式{' '}
                <select
                  aria-label={`第 ${i + 1} 轮形式`}
                  value={r.format}
                  onChange={(e) =>
                    updateRound(i, { format: e.target.value as PositionInterviewRound['format'] })
                  }
                >
                  <option value="video">视频</option>
                  <option value="onsite">现场</option>
                  <option value="phone">电话</option>
                  <option value="ai">AI 初面</option>
                </select>
              </label>
              <label>
                时长{' '}
                <select
                  aria-label={`第 ${i + 1} 轮时长`}
                  value={r.duration}
                  onChange={(e) =>
                    updateRound(i, {
                      duration: Number(e.target.value) as PositionInterviewRound['duration'],
                    })
                  }
                >
                  {[15, 30, 45, 60, 90].map((n) => (
                    <option value={n} key={n}>
                      {n} 分钟
                    </option>
                  ))}
                </select>
              </label>
              <DirectoryPersonPicker
                id={`round-${i}`}
                label={`第 ${i + 1} 轮面试官`}
                dept={pos.dept}
                value={r.interviewers}
                multiple
                disabled={locked}
                onChange={(ids) => updateRound(i, { interviewers: ids })}
              />
              <label>
                通过规则{' '}
                <select
                  value={r.rule}
                  onChange={(e) =>
                    updateRound(i, { rule: e.target.value as PositionInterviewRound['rule'] })
                  }
                >
                  <option value="unanimous">一致通过</option>
                  <option value="majority">多数通过</option>
                  <option value="designated">指定人决定</option>
                </select>
              </label>
              {r.rule === 'designated' && (
                <DirectoryPersonPicker
                  id={`decider-${i}`}
                  label={`第 ${i + 1} 轮决定人`}
                  dept={pos.dept}
                  value={r.decision_by ? [r.decision_by] : []}
                  disabled={locked}
                  onChange={(ids) => updateRound(i, { decision_by: ids[0] })}
                />
              )}
              <label>
                评价项
                <Input.TextArea
                  aria-label={`第 ${i + 1} 轮评价项`}
                  value={r.criteria}
                  maxLength={2000}
                  onChange={(e) => updateRound(i, { criteria: e.target.value })}
                />
              </label>
              <Space>
                <Button
                  disabled={locked || i === 0}
                  onClick={() => {
                    const next = [...rounds];
                    [next[i - 1], next[i]] = [next[i]!, next[i - 1]!];
                    set({ rounds: next });
                  }}
                >
                  上移
                </Button>
                <Button
                  disabled={locked}
                  onClick={() => set({ rounds: rounds.filter((_, n) => n !== i) })}
                >
                  移除此轮
                </Button>
              </Space>
            </div>
          ))}
          <Button
            disabled={locked || rounds.length >= 6}
            onClick={() =>
              set({
                rounds: [
                  ...rounds,
                  {
                    name: '',
                    format: 'video',
                    duration: 30,
                    interviewers: [],
                    rule: 'unanimous',
                    criteria: '',
                  },
                ],
              })
            }
          >
            添加轮次
          </Button>
        </>
      )}
    </div>
  );
}

export function PositionContentPanels({
  pos,
  onAction,
}: {
  pos: LivePosition;
  onAction: (action: Action, patch?: Partial<PositionCommand>) => void;
}) {
  const api = useApi();
  const [preview, setPreview] = useState(false);
  const [asked, setAsked] = useState(false);
  const knowledge = useQuery({
    queryKey: ['position-knowledge-preview', pos.id, pos.version, asked],
    queryFn: () => api.positionKnowledgePreview(pos.id, asked),
    enabled: preview,
  });
  const writable = pos.status !== 'closed';
  return (
    <>
      <p>必问项：{pos.profile.must_ask || '未填写'}</p>
      <details>
        <summary>画像版本历史与对比</summary>
        <Table
          pagination={false}
          rowKey="version"
          dataSource={[...pos.profiles].reverse()}
          columns={[
            { title: '版本', dataIndex: 'version' },
            {
              title: '生效状态',
              render: (_, p) =>
                pos.activeProfile?.version === p.version
                  ? '当前生效'
                  : p.confirmedBy
                    ? '历史版本'
                    : '待确认 / 已被修订',
            },
            { title: '必备条件', dataIndex: 'must' },
            {
              title: '加分项',
              render: (_, p) => (
                <span style={{ whiteSpace: 'pre-wrap' }}>
                  {p.plus
                    .split('\n')
                    .filter(Boolean)
                    .map(
                      (s, i) =>
                        `${s}（${{ high: '高', medium: '中', low: '低' }[p.plus_weights[i] ?? 'medium']}）`,
                    )
                    .join('\n')}
                </span>
              ),
            },
            { title: '不合适信号', dataIndex: 'redflag' },
            { title: '必问项', dataIndex: 'must_ask' },
          ]}
        />
      </details>
      <h2>JD 与发布规则</h2>
      <p>
        当前编辑：第 {pos.jd.version} 版 · {JD_STATUS[pos.jd.status]}；生效：
        {pos.activeJd ? `第 ${pos.activeJd.version} 版` : '尚未发布'}；审批：
        {pos.jdApprovalRequired ? '需要招聘负责人审批' : '未开启审批'}
      </p>
      <pre style={{ whiteSpace: 'pre-wrap' }}>{pos.jd.content}</pre>
      {pos.jd.reason && <p>审批意见：{pos.jd.reason}</p>}
      {writable && (
        <Space wrap>
          {pos.canEdit && <Button onClick={() => onAction('save_jd')}>编辑 JD</Button>}
          {pos.canLead && (
            <Button onClick={() => onAction('configure_publish')}>发布审批设置</Button>
          )}
          {pos.canApproveJd && (
            <>
              <Button onClick={() => onAction('approve_jd')}>批准 JD</Button>
              <Button onClick={() => onAction('reject_jd')}>驳回 JD</Button>
            </>
          )}
          {pos.canEdit && ['open', 'paused'].includes(pos.status) && (
            <Button onClick={() => onAction('apply_jd')}>启用新版 JD</Button>
          )}
        </Space>
      )}
      <details>
        <summary>JD 版本历史与对比</summary>
        {[...pos.jdVersions].reverse().map((j) => (
          <article key={j.version}>
            <h3>
              第 {j.version} 版 · {JD_STATUS[j.status]}
            </h3>
            <pre style={{ whiteSpace: 'pre-wrap' }}>{j.content}</pre>
          </article>
        ))}
      </details>
      <h2>岗位知识库</h2>
      {writable && pos.canCollaborate && (
        <Button
          onClick={() => onAction('save_kb', { content: '', source: '', disclosure: 'internal' })}
        >
          新增知识条目
        </Button>
      )}
      <Table<KnowledgeEntry>
        rowKey="id"
        pagination={{ pageSize: 5 }}
        dataSource={pos.knowledge.filter((e) => e.active)}
        columns={[
          { title: '内容', dataIndex: 'content' },
          { title: '来源', dataIndex: 'source' },
          { title: '披露', render: (_, e) => DISCLOSURE[e.disclosure] },
          {
            title: '操作',
            render: (_, e) =>
              writable &&
              pos.canCollaborate && (
                <Space>
                  <Button
                    onClick={() =>
                      onAction('save_kb', {
                        entry_id: e.id,
                        content: e.content,
                        source: e.source,
                        disclosure: e.disclosure,
                      })
                    }
                  >
                    修订条目
                  </Button>
                  <Button danger onClick={() => onAction('retire_kb', { entry_id: e.id })}>
                    下线条目
                  </Button>
                </Space>
              ),
          },
        ]}
      />
      <Space>
        <Button onClick={() => setPreview((v) => !v)}>对外答复预览</Button>
        <Checkbox checked={asked} onChange={(e) => setAsked(e.target.checked)}>
          候选人已问到
        </Checkbox>
      </Space>
      {preview && (
        <div aria-label="对外知识预览">
          {knowledge.isError && (
            <Alert type="error" message={toAppError(knowledge.error).message} />
          )}
          {knowledge.data?.needsHuman && <p>存在需人工确认的内容；未获依据的问题应转人工。</p>}
          {knowledge.data?.entries.map((e) => (
            <p key={e.id}>
              {e.content} · {e.source}
            </p>
          ))}
          {knowledge.data?.entries.length === 0 && <p>没有允许对外披露的知识。</p>}
        </div>
      )}
      <details>
        <summary>知识库修订与下线历史</summary>
        {pos.knowledge.map((e) => (
          <p key={e.id}>
            <Tag>{e.active ? '有效' : '失效'}</Tag>
            {e.id} · 第 {e.version} 版 · {DISCLOSURE[e.disclosure]} · {e.content} · {e.source}
          </p>
        ))}
      </details>
      <h2>来源与协作</h2>
      <p>
        负责 HR：{pos.ownerHr}；共享 HR：{pos.sharedMembers.map((m) => m.name).join('、') || '无'}
        ；用人经理：{pos.hiringManager}
      </p>
      {writable && (
        <Space>
          {pos.canShare && <Button onClick={() => onAction('share')}>共享协作</Button>}
          {pos.canCollaborate && (
            <Button onClick={() => onAction('comment', { content: '', mentions: [] })}>
              添加留言
            </Button>
          )}
        </Space>
      )}
      {pos.comments.map((c) => (
        <p key={c.id}>
          <strong>{c.authorName}</strong> · {new Date(c.at).toLocaleString('zh-CN')}
          <br />
          {c.content}
          {c.mentions.length > 0 &&
            ` · 提及 ${c.mentions.map((id) => (id === pos.managerId ? pos.hiringManager : id === pos.ownerId ? pos.ownerHr : (pos.sharedMembers.find((m) => m.id === id)?.name ?? id))).join('、')}`}
        </p>
      ))}
      <h2>面试流程</h2>
      {writable && pos.canEdit && (
        <Button onClick={() => onAction('save_interview_plan')}>编辑面试流程</Button>
      )}
      <p>新进入面试阶段的候选人使用最新流程，已在途的面试保留进入时的版本。</p>
      <Link to={`/interviews?position_id=${encodeURIComponent(pos.id)}`}>
        查看本岗位面试日程与面评
      </Link>
      <PositionInterviewSchedule id={pos.id} />
      {pos.interviewPlans.at(-1)?.rounds.map((r, i) => (
        <p key={i}>
          第 {i + 1} 轮：{r.name} · {r.duration} 分钟 · {r.criteria}
        </p>
      ))}
      <details>
        <summary>面试流程历史</summary>
        {pos.interviewPlans.map((p) => (
          <div key={p.version}>
            <strong>第 {p.version} 版</strong>
            {p.rounds.map((r, i) => (
              <p key={i}>
                {i + 1}. {r.name} · {r.duration} 分钟 · {r.criteria}
              </p>
            ))}
          </div>
        ))}
      </details>
    </>
  );
}

function PositionInterviewSchedule({ id }: { id: string }) {
  const api = useApi();
  const query = useQuery({
    queryKey: ['position-interviews', id],
    queryFn: () => api.liveInterviews(1, { position_id: id }),
    refetchInterval: 5000,
  });
  return (
    <section aria-label="本岗位面试记录">
      <p>共 {query.data?.total ?? 0} 场面试</p>
      {query.isError && <Alert type="error" message={toAppError(query.error).message} />}
      {query.data?.items.map((iv) => (
        <p key={iv.id}>
          <Link to={`/interviews/${iv.id}`}>
            {iv.candidate_name} · 第 {iv.round_no} 轮 {iv.round_name}
          </Link>{' '}
          · {iv.start ? new Date(iv.start).toLocaleString() : '待约'}
        </p>
      ))}
    </section>
  );
}
