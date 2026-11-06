import { useState } from 'react';
import { Alert, Button, Checkbox, Input, Modal, Space, Table } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  useApi,
  toAppError,
  type LiveApplication,
  type ApplicationCommand,
  type AttachCommand,
} from '@recruiter/api-client';
import { useLiveWrite } from './useLiveWrite';

export const STAGE_LABEL: Record<string, string> = {
  reach: 'AI 触达',
  talking: '沟通中',
  ai_eval: 'AI 评估',
  interview: '面试',
  manager_eval: '用人部门评估',
  hired: '已录用',
  rejected: '已淘汰',
  withdrawn: '候选人放弃',
  transferred: '已转岗位',
  position_closed: '岗位关闭终止',
  declined: '未接受录用',
  no_show: '未入职',
  joined: '已入职',
};
const ACTION_LABEL: Record<ApplicationCommand['action'], string> = {
  advance: '推进下一阶段',
  reject: '淘汰候选人',
  withdraw: '候选人放弃',
  rollback: '回退阶段',
  undo_reject: '撤销淘汰',
  transfer: '转到其他岗位',
};

export function AttachDialog({
  candidateId,
  positionId,
  onClose,
}: {
  candidateId?: string;
  positionId?: string;
  onClose: () => void;
}) {
  const api = useApi();
  const cache = useQueryClient();
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState('');
  const [reason, setReason] = useState('');
  const [evidence, setEvidence] = useState('');
  const [source, setSource] = useState<'hr' | 'candidate'>('hr');
  const options = useQuery({
    queryKey: ['attach-options', candidateId, query, page],
    queryFn: async () =>
      candidateId
        ? api.positionPage(page, 'open', { query }).then((r) => ({
            ...r,
            items: r.items.filter((p) => p.canEdit).map((p) => ({ id: p.id, name: p.name })),
          }))
        : api.candidatePage(page, { query }).then((r) => ({
            ...r,
            items: r.items
              .filter((c) => !c.do_not_contact && c.consent !== 'revoked')
              .map((c) => ({ id: c.id, name: c.profile.name })),
          })),
  });
  const op = useLiveWrite<AttachCommand, LiveApplication>(
    (body, opts) => api.attachCandidate(body, opts),
    () => {
      void cache.invalidateQueries();
      onClose();
    },
  );
  return (
    <Modal
      open
      title={candidateId ? '挂到其他岗位' : '从人才库挂人'}
      onCancel={onClose}
      footer={null}
      maskClosable={!op.busy}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Input.Search
          aria-label="搜索挂入对象"
          placeholder={candidateId ? '搜索招聘中岗位' : '搜索候选人'}
          onSearch={(q) => {
            setQuery(q);
            setPage(1);
            setSelected('');
          }}
          disabled={op.locked}
        />
        <label>
          {candidateId ? '目标岗位' : '选择候选人'}
          <select
            aria-label={candidateId ? '目标岗位' : '选择候选人'}
            value={selected}
            disabled={op.locked}
            onChange={(e) => setSelected(e.target.value)}
            style={{ width: '100%', padding: 8 }}
          >
            <option value="">请选择</option>
            {options.data?.items.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name} · {o.id.slice(-6)}
              </option>
            ))}
          </select>
        </label>
        <Space>
          <Button
            disabled={page === 1 || op.locked}
            onClick={() => {
              setPage((p) => p - 1);
              setSelected('');
            }}
          >
            上一页
          </Button>
          <span>第 {page} 页</span>
          <Button
            disabled={page * 20 >= (options.data?.total ?? 0) || op.locked}
            onClick={() => {
              setPage((p) => p + 1);
              setSelected('');
            }}
          >
            下一页
          </Button>
        </Space>
        {options.isError && (
          <Alert role="alert" type="error" message={toAppError(options.error).message} />
        )}
        <label>
          挂入来源
          <select
            aria-label="挂入来源"
            value={source}
            disabled={op.locked}
            onChange={(e) => setSource(e.target.value as typeof source)}
          >
            <option value="hr">HR 推荐</option>
            <option value="candidate">候选人主动投递</option>
          </select>
        </label>
        <Input.TextArea
          aria-label="强制挂入原因"
          placeholder="冷却期内强制挂入须填写原因"
          value={reason}
          disabled={op.locked}
          onChange={(e) => setReason(e.target.value)}
        />
        {source === 'candidate' && (
          <Input
            aria-label="主动投递证据"
            placeholder="投递记录编号或证据引用"
            value={evidence}
            disabled={op.locked}
            onChange={(e) => setEvidence(e.target.value)}
          />
        )}
        <Button
          type="primary"
          loading={op.busy}
          disabled={!selected || op.locked}
          onClick={() =>
            void op.submit({
              candidate_id: candidateId ?? selected,
              position_id: positionId ?? selected,
              source,
              reason,
              evidence,
            })
          }
        >
          确认挂入
        </Button>
        {op.feedback}
      </Space>
    </Modal>
  );
}

function ActionDialog({
  app,
  action,
  onClose,
}: {
  app: LiveApplication;
  action: ApplicationCommand['action'];
  onClose: () => void;
}) {
  const api = useApi();
  const cache = useQueryClient();
  const [reason, setReason] = useState('');
  const [reasonCode, setReasonCode] = useState<ApplicationCommand['reason_code']>('');
  const [notify, setNotify] = useState(false);
  const [stage, setStage] = useState<ApplicationCommand['target_stage']>('reach');
  const [target, setTarget] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const positions = useQuery({
    queryKey: ['transfer-positions', query, page],
    queryFn: () => api.positionPage(page, 'open', { query }),
    enabled: action === 'transfer',
  });
  const op = useLiveWrite<ApplicationCommand, LiveApplication>(
    (body, opts) => api.liveApplicationCommand(app.id, body, opts),
    () => {
      void cache.invalidateQueries();
      onClose();
    },
  );
  return (
    <Modal
      open
      title={ACTION_LABEL[action]}
      footer={null}
      onCancel={onClose}
      maskClosable={!op.busy}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <p>
          {app.position_name} · 当前：{STAGE_LABEL[app.outcome ?? app.stage ?? '']}
        </p>
        {action === 'reject' && (
          <>
            <Alert
              type="info"
              message="可安排下一个工作日北京时间 10 点在候选人 H5 页面发布结束通知；送达前可撤销淘汰。"
            />
            <Checkbox
              checked={notify}
              disabled={op.locked}
              onChange={(e) => setNotify(e.target.checked)}
            >
              安排 H5 结束通知
            </Checkbox>
            <label>
              淘汰原因分类
              <select
                aria-label="淘汰原因分类"
                disabled={op.locked}
                value={reasonCode}
                onChange={(e) => setReasonCode(e.target.value as typeof reasonCode)}
              >
                <option value="">请选择</option>
                {Object.entries({
                  requirements: '不符合必备条件',
                  experience: '经验不匹配',
                  skills: '技能不匹配',
                  salary: '薪资不匹配',
                  location: '地点不匹配',
                  other: '其他',
                }).map(([v, t]) => (
                  <option key={v} value={v}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        {action === 'rollback' && (
          <label>
            回退到
            <select
              aria-label="回退到"
              disabled={op.locked}
              value={stage}
              onChange={(e) => setStage(e.target.value as typeof stage)}
            >
              {['reach', 'talking', 'ai_eval', 'interview', 'manager_eval'].map((v) => (
                <option key={v} value={v}>
                  {STAGE_LABEL[v]}
                </option>
              ))}
            </select>
          </label>
        )}
        {action === 'transfer' && (
          <>
            <Input.Search
              aria-label="搜索转入岗位"
              onSearch={(q) => {
                setQuery(q);
                setPage(1);
                setTarget('');
              }}
            />
            <select
              aria-label="转入岗位"
              value={target}
              disabled={op.locked}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">请选择</option>
              {positions.data?.items
                .filter((p) => p.id !== app.position_id && p.canEdit)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </select>
            <Space>
              <Button disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
                上一页
              </Button>
              <Button
                disabled={page * 20 >= (positions.data?.total ?? 0)}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页
              </Button>
            </Space>
          </>
        )}
        {action !== 'advance' && (
          <Input.TextArea
            aria-label="操作原因"
            placeholder="请填写原因"
            disabled={op.locked}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        )}
        <Button
          type="primary"
          disabled={op.locked}
          loading={op.busy}
          onClick={() =>
            void op.submit({
              action,
              expected_version: app.version,
              reason,
              reason_code: reasonCode,
              notify: action === 'reject' && notify,
              ...(action === 'rollback' ? { target_stage: stage } : {}),
              ...(action === 'transfer' ? { target_position_id: target } : {}),
            })
          }
        >
          确认操作
        </Button>
        {op.feedback}
      </Space>
    </Modal>
  );
}

export function LiveApplicationTable({ rows }: { rows: LiveApplication[] }) {
  const [editing, setEditing] = useState<{
    app: LiveApplication;
    action: ApplicationCommand['action'];
  }>();
  return (
    <>
      <Table
        rowKey="id"
        dataSource={rows}
        pagination={{ pageSize: 10 }}
        scroll={{ x: 860 }}
        columns={[
          {
            title: '候选人',
            render: (_, a: LiveApplication) =>
              a.candidate_id ? (
                <Link to={`/candidates/${a.candidate_id}`}>{a.candidate_name}</Link>
              ) : (
                '范围外记录'
              ),
          },
          {
            title: '岗位',
            render: (_, a: LiveApplication) =>
              a.restricted ? (
                a.position_name
              ) : (
                <Link to={`/positions/${a.position_id}`}>{a.position_name}</Link>
              ),
          },
          {
            title: '开始时间',
            render: (_, a: LiveApplication) => new Date(a.started_at).toLocaleDateString('zh-CN'),
          },
          {
            title: '阶段 / 结论',
            render: (_, a: LiveApplication) =>
              STAGE_LABEL[a.outcome ?? a.stage ?? ''] ?? '仅显示结论',
          },
          {
            title: '原因',
            render: (_, a: LiveApplication) => a.reason ?? (a.restricted ? '超出数据范围' : '—'),
          },
          {
            title: '操作',
            render: (_, a: LiveApplication) =>
              a.can_edit && (
                <Space wrap>
                  {(a.outcome
                    ? a.outcome === 'rejected'
                      ? ['undo_reject']
                      : []
                    : [
                        'advance',
                        'reject',
                        'withdraw',
                        ...(a.can_rollback ? ['rollback'] : []),
                        'transfer',
                      ]
                  ).map((key) => (
                    <Button
                      size="small"
                      key={key}
                      onClick={() =>
                        setEditing({ app: a, action: key as ApplicationCommand['action'] })
                      }
                    >
                      {ACTION_LABEL[key as ApplicationCommand['action']]}
                    </Button>
                  ))}
                </Space>
              ),
          },
        ]}
      />
      {editing && <ActionDialog {...editing} onClose={() => setEditing(undefined)} />}
    </>
  );
}

export function LivePositionCandidates({
  positionId,
  canEdit,
}: {
  positionId: string;
  canEdit: boolean;
}) {
  const api = useApi();
  const [attach, setAttach] = useState(false);
  const q = useQuery({
    queryKey: ['live-position-applications', positionId],
    queryFn: () => api.livePositionApplications(positionId),
    refetchInterval: 4000,
  });
  return (
    <section aria-label="岗位候选人">
      <h2>候选人 · {q.data?.filter((a) => !a.outcome).length ?? 0} 人进行中</h2>
      {canEdit && <Button onClick={() => setAttach(true)}>从人才库挂人</Button>}
      {q.isError && <Alert role="alert" type="error" message={toAppError(q.error).message} />}
      <LiveApplicationTable rows={q.data ?? []} />
      {attach && <AttachDialog positionId={positionId} onClose={() => setAttach(false)} />}
    </section>
  );
}
