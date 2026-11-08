import { useRef, useState } from 'react';
import {
  Alert,
  Button,
  Descriptions,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Timeline,
} from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import {
  newIdempotencyKey,
  toAppError,
  useApi,
  type LivePosition,
  type PositionCommand,
  type WriteOpts,
} from '@recruiter/api-client';
import { DirectoryPersonPicker } from '@recruiter/ui-kit/directory-person-picker';
import { POSITION_STATUS_LABEL } from '@recruiter/domain';
import { PositionContentPanels, ExtendedPositionForm } from './PositionContentPanels';
import { LivePositionCandidates } from '../../../shared/LiveApplications';

const ACTIONS: Record<string, string> = {
  assign: '指定负责 HR',
  save_profile: '编辑画像与 JD',
  confirm_profile: '确认画像',
  publish: '发布岗位',
  pause: '暂停招聘',
  resume: '恢复招聘',
  close: '关闭岗位',
  created: '生成岗位',
  merged: '合并需求',
  save_jd: '编辑 JD',
  approve_jd: '批准 JD',
  reject_jd: '驳回 JD',
  apply_jd: '启用新版 JD',
  configure_publish: '发布审批设置',
  save_kb: '保存知识条目',
  retire_kb: '下线知识条目',
  share: '共享协作',
  comment: '添加留言',
  request_close: '申请关闭',
  confirm_close: '确认关闭',
  reject_close: '驳回关闭',
  save_interview_plan: '编辑面试流程',
  amend_confirm_profile: '修改并确认画像',
};

function useOperation<T>(
  operation: (body: T, opts: WriteOpts) => Promise<unknown>,
  success: () => void,
) {
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<{ body: T; key: string }>();
  return {
    busy,
    retry,
    error,
    locked: busy || retry || conflict,
    conflict,
    submit: async (body: T) => {
      if (busy || conflict) return;
      pending.current ??= { body, key: newIdempotencyKey() };
      setBusy(true);
      setError('');
      try {
        await operation(pending.current.body, { idempotencyKey: pending.current.key });
        pending.current = undefined;
        setRetry(false);
        success();
      } catch (e) {
        const err = toAppError(e);
        const uncertain = err.status === 0 || err.status >= 500;
        setRetry(uncertain);
        setConflict(err.status === 409);
        if (!uncertain) pending.current = undefined;
        setError(
          err.message + (err.status === 409 ? '。输入已保留，请关闭后刷新并重新核对。' : ''),
        );
      } finally {
        setBusy(false);
      }
    },
  };
}

export function LivePositionList() {
  const api = useApi();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [view, setView] = useState('all');
  const [search, setSearch] = useState('');
  const query = useQuery({
    queryKey: ['live-positions', page, status, view, search],
    queryFn: () => api.positionPage(page, status, { view, query: search }),
    refetchInterval: 5000,
  });
  return (
    <div>
      <h1>岗位管理</h1>
      <p>岗位来自已通过的招聘需求。同岗需求可选择合并或新建，生成后先确认画像再发布。</p>
      <Space style={{ marginBottom: 16 }}>
        <Select
          aria-label="岗位范围"
          value={view}
          style={{ width: 140 }}
          options={[
            { value: 'all', label: '全部岗位' },
            { value: 'mine', label: '我负责的' },
            { value: 'participating', label: '我参与的' },
          ]}
          onChange={(v) => {
            setView(v);
            setPage(1);
          }}
        />
        <Input.Search
          aria-label="搜索岗位"
          placeholder="搜索岗位名称"
          allowClear
          onSearch={(v) => {
            setSearch(v);
            setPage(1);
          }}
        />
      </Space>
      <Select
        aria-label="岗位状态"
        value={status}
        style={{ width: 180, marginBottom: 16 }}
        onChange={(v) => {
          setStatus(v);
          setPage(1);
        }}
        options={[
          { value: '', label: '全部状态' },
          ...Object.entries(POSITION_STATUS_LABEL).map(([value, label]) => ({ value, label })),
        ]}
      />
      {query.isError && (
        <Alert
          type="error"
          message={toAppError(query.error).message}
          action={<Button onClick={() => void query.refetch()}>重试</Button>}
        />
      )}
      <Table<LivePosition>
        rowKey="id"
        loading={query.isFetching}
        dataSource={query.data?.items ?? []}
        pagination={{
          current: page,
          pageSize: 20,
          total: query.data?.total ?? 0,
          showSizeChanger: false,
          onChange: setPage,
        }}
        columns={[
          {
            title: '岗位',
            render: (_, p) => (
              <>
                <Link to={`/positions/${p.id}`}>{p.name}</Link>
                <div>
                  {p.dept} · {p.city} · {p.level}
                </div>
              </>
            ),
          },
          { title: '状态', render: (_, p) => POSITION_STATUS_LABEL[p.status] },
          { title: '计划人数', dataIndex: 'planned' },
          { title: '负责 HR', dataIndex: 'ownerHr' },
          { title: '用人经理', dataIndex: 'hiringManager' },
          { title: '期望到岗', dataIndex: 'expectedOnboard' },
        ]}
      />
    </div>
  );
}

function PositionAction({
  pos,
  action,
  onClose,
  onSuccess,
  patch,
}: {
  pos: LivePosition;
  action: PositionCommand['action'];
  onClose: () => void;
  onSuccess: () => void;
  patch?: Partial<PositionCommand>;
}) {
  const api = useApi();
  const [body, setBody] = useState<PositionCommand>({
    expected_version: pos.version,
    action,
    must: pos.profile.must,
    plus: pos.profile.plus,
    redflag: pos.profile.redflag,
    jd: pos.jd.content,
    must_ask: pos.profile.must_ask,
    plus_weights: pos.profile.plus_weights,
    jd_approval_required: pos.jdApprovalRequired,
    shared_ids: pos.sharedIds,
    rounds: pos.interviewPlans.at(-1)?.rounds ?? [],
    handling: 'continue',
    owner_id: pos.ownerId ?? '',
    ...patch,
  });
  const op = useOperation<PositionCommand>(
    (command, opts) => api.positionCommand(pos.id, command, opts),
    onSuccess,
  );
  const set = (patch: Partial<PositionCommand>) => setBody((b) => ({ ...b, ...patch }));
  return (
    <Modal open title={ACTIONS[action]} onCancel={onClose} footer={null} maskClosable={false}>
      <fieldset disabled={op.locked} style={{ border: 0, padding: 0 }}>
        {action === 'assign' && (
          <>
            <label htmlFor="position-owner">负责 HR</label>
            <DirectoryPersonPicker
              id="position-owner"
              label="负责 HR"
              dept={pos.dept}
              value={body.owner_id ? [body.owner_id] : []}
              disabled={op.locked}
              onChange={(ids) => set({ owner_id: ids[0] ?? '' })}
            />
            <p>请选择具备本部门招聘权限的在职 HR。</p>
          </>
        )}
        {action === 'save_profile' &&
          (['must', 'plus', 'redflag', 'jd', 'must_ask'] as const).map((key, i) => (
            <div key={key} style={{ marginBottom: 12 }}>
              <label htmlFor={`profile-${key}`}>
                {['必备条件', '加分项', '不合适信号', 'JD 岗位职责', '必问项'][i]}
              </label>
              <Input.TextArea
                id={`profile-${key}`}
                value={body[key]}
                maxLength={key === 'jd' ? 4000 : 2000}
                autoSize={{ minRows: 2, maxRows: 6 }}
                onChange={(e) =>
                  set({
                    [key]: e.target.value,
                    ...(key === 'plus'
                      ? {
                          plus_weights: e.target.value
                            .split('\n')
                            .filter((s) => s.trim())
                            .map((_, idx) => body.plus_weights?.[idx] ?? 'medium'),
                        }
                      : {}),
                  })
                }
              />
            </div>
          ))}
        {action === 'pause' && (
          <>
            <label htmlFor="position-reason">暂停原因</label>
            <Input.TextArea
              id="position-reason"
              value={body.reason}
              maxLength={500}
              onChange={(e) => set({ reason: e.target.value })}
            />
            <label htmlFor="position-handling">在途处理方式</label>
            <select
              id="position-handling"
              value={body.handling}
              onChange={(e) => set({ handling: e.target.value as 'continue' | 'freeze' })}
            >
              <option value="continue">继续推进</option>
              <option value="freeze">冻结</option>
            </select>
          </>
        )}
        {(action === 'close' || action === 'request_close') && (
          <>
            <label htmlFor="position-close-reason">关闭原因</label>
            <select
              id="position-close-reason"
              value={body.reason ?? ''}
              onChange={(e) => set({ reason: e.target.value })}
            >
              <option value="">请选择</option>
              {['招满', '需求取消', '组织调整', '其他'].map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
            <p>
              {action === 'request_close'
                ? '提交给用人经理确认，确认前继续保留当前状态及编制预占。'
                : '关闭后不能直接恢复招聘；释放本岗位尚未使用的正式编制预占。'}
            </p>
          </>
        )}
        {action === 'confirm_profile' && (
          <p>确认第 {pos.profile.version} 版画像及 JD 职责；之后编辑会要求重新确认。</p>
        )}
        {action === 'publish' && (
          <p>将岗位状态更新为招聘中。当前尚未接入外部招聘渠道，不会向外部发布内容。</p>
        )}
        {action === 'resume' && <p>将岗位状态恢复为招聘中。</p>}
        <ExtendedPositionForm pos={pos} body={body} set={set} locked={op.locked} />
      </fieldset>
      {op.error && <Alert role="alert" type="error" message={op.error} />}
      <Space style={{ marginTop: 16 }}>
        <Button onClick={onClose}>关闭弹窗</Button>
        <Button
          type="primary"
          loading={op.busy}
          disabled={op.conflict}
          onClick={() => void op.submit(body)}
        >
          {op.retry ? '重试本次操作' : '确认操作'}
        </Button>
      </Space>
    </Modal>
  );
}

export function LivePositionDetail() {
  const { id = '' } = useParams();
  const api = useApi();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['live-position', id],
    queryFn: () => api.positionDetail(id),
  });
  const [editing, setEditing] = useState<{
    pos: LivePosition;
    action: PositionCommand['action'];
    patch?: Partial<PositionCommand>;
  }>();
  if (query.isPending) return <Spin />;
  if (!query.data) return <Alert type="error" message={toAppError(query.error).message} />;
  const pos = query.data;
  const refresh = () => {
    setEditing(undefined);
    void query.refetch();
    void qc.invalidateQueries({ queryKey: ['live-positions'] });
    void qc.invalidateQueries({ queryKey: ['position-generation'] });
  };
  const actions: PositionCommand['action'][] = [];
  if (pos.canAssign && pos.status !== 'closed') actions.push('assign');
  if (pos.status !== 'closed') {
    if (pos.canEdit) actions.push('save_profile');
    if (pos.canEdit && pos.status === 'to_publish') actions.push('publish');
    if (pos.canConfirm && !pos.profile.confirmedBy) actions.push('confirm_profile');
  }
  if (pos.canEdit && pos.status === 'open') actions.push('pause');
  if (pos.canEdit && pos.status === 'paused') actions.push('resume');
  if (pos.canClose && ['open', 'paused'].includes(pos.status)) actions.push('close');
  if (pos.canEdit && !pos.canClose && ['open', 'paused'].includes(pos.status) && !pos.closeRequest)
    actions.push('request_close');
  if (pos.canConfirm && pos.closeRequest && pos.status !== 'closed')
    actions.push('confirm_close', 'reject_close');
  return (
    <div>
      <Link to="/positions">返回岗位列表</Link>
      <h1>
        {pos.name} <small>{POSITION_STATUS_LABEL[pos.status]}</small>
      </h1>
      {pos.canEdit && (
        <p>
          <Link to={`/ai-jobs?component=A1&object=${encodeURIComponent(pos.id)}`}>
            生成画像草稿
          </Link>{' '}
          ·{' '}
          <Link to={`/ai-jobs?component=A2&object=${encodeURIComponent(pos.id)}`}>
            简历匹配与人才搜索
          </Link>{' '}
          ·{' '}
          <Link to={`/ai-jobs?component=A7&object=${encodeURIComponent(pos.id)}`}>
            岗位数据洞察
          </Link>
        </p>
      )}
      <Space wrap style={{ marginBottom: 16 }}>
        {actions.map((a) => (
          <Button
            key={a}
            danger={a === 'close'}
            disabled={
              a === 'publish' &&
              (!pos.profile.confirmedBy ||
                !pos.ownerId ||
                (pos.jdApprovalRequired && pos.jd.status !== 'approved'))
            }
            onClick={() => setEditing({ pos, action: a })}
          >
            {ACTIONS[a]}
          </Button>
        ))}
        <Button onClick={() => void query.refetch()}>刷新岗位</Button>
      </Space>
      {pos.status === 'to_publish' && !pos.profile.confirmedBy && (
        <p>发布前请先由用人经理确认画像。</p>
      )}
      {pos.closeRequest && (
        <Alert type="warning" message={`待用人经理确认关闭：${pos.closeRequest.reason}`} />
      )}
      <Alert
        type="info"
        message="当前支持岗位内部流转；候选人、渠道投递与 AI 画像生成将在后续批次接入。画像初稿来自已审批需求，请人工核对。"
        style={{ marginBottom: 16 }}
      />
      <Descriptions
        bordered
        column={2}
        items={[
          { label: '岗位编号', children: pos.id },
          { label: '版本', children: pos.version },
          { label: '部门', children: pos.dept },
          { label: '城市 / 职级', children: `${pos.city} / ${pos.level}` },
          { label: '计划人数', children: pos.planned },
          { label: '已录用人数', children: pos.hired },
          { label: '负责 HR', children: pos.ownerHr },
          { label: '用人经理', children: pos.hiringManager },
          { label: '保密岗位', children: pos.confidential ? '是' : '否' },
          { label: '期望到岗', children: pos.expectedOnboard },
          {
            label: '来源需求',
            children: (
              <Space direction="vertical">
                {pos.requisitionIds.map((reqId) => (
                  <Link key={reqId} to={`/requisitions/${reqId}`}>
                    {reqId}
                  </Link>
                ))}
              </Space>
            ),
          },
        ]}
      />
      <h2>岗位画像与 JD · 第 {pos.profile.version} 版</h2>
      <p>{pos.profile.confirmedBy ? '画像已确认' : '待用人经理确认'}</p>
      <p>
        当前生效画像：{pos.activeProfile ? `第 ${pos.activeProfile.version} 版` : '尚无生效版本'}
        。待确认的新版本不替换当前生效版本。
      </p>
      <Descriptions
        bordered
        column={1}
        items={(['must', 'plus', 'redflag', 'jd'] as const).map((key, i) => ({
          label: ['必备条件', '加分项', '不合适信号', 'JD 岗位职责'][i],
          children: <span style={{ whiteSpace: 'pre-wrap' }}>{pos.profile[key] || '未填写'}</span>,
        }))}
      />
      <PositionContentPanels
        pos={pos}
        onAction={(action, patch) => setEditing({ pos, action, patch })}
      />
      <LivePositionCandidates positionId={pos.id} canEdit={pos.canEdit && pos.status === 'open'} />
      <h2>操作记录</h2>
      <Timeline
        items={pos.history.map((h, i) => ({
          key: i,
          children: (
            <span>
              {ACTIONS[h.action] ?? h.action} · {h.actorName} ·{' '}
              {new Date(h.at).toLocaleString('zh-CN')}
              {h.reason ? ` · ${h.reason}` : ''}
            </span>
          ),
        }))}
      />
      {editing && (
        <PositionAction
          key={`${editing.pos.version}-${editing.action}`}
          {...editing}
          onClose={refresh}
          onSuccess={refresh}
        />
      )}
    </div>
  );
}

export function PositionGenerationPanel({ reqId }: { reqId: string }) {
  const api = useApi();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['position-generation', reqId],
    queryFn: () => api.positionGeneration(reqId),
    refetchInterval: 3000,
  });
  const [target, setTarget] = useState('');
  const op = useOperation<{ expected_version: number; target_id?: string }>(
    (body, opts) => api.resolvePositionGeneration(reqId, body, opts),
    () => {
      void query.refetch();
      void qc.invalidateQueries({ queryKey: ['live-positions'] });
    },
  );
  const data = query.data;
  return (
    <div style={{ margin: '16px 0' }}>
      {query.isError ? (
        <Alert type="error" message={toAppError(query.error).message} />
      ) : data?.position ? (
        <Link to={`/positions/${data.position.id}`}>
          生成的岗位：{data.position.name} · {POSITION_STATUS_LABEL[data.position.status]}
        </Link>
      ) : data?.status === 'decision' ? (
        <>
          <Alert
            type="warning"
            message="存在可合并的同岗需求，请负责 HR 选择合并或新建独立岗位。"
          />
          {data.dueAt && (
            <p>
              处理截止：{new Date(data.dueAt).toLocaleString('zh-CN')}；超时将自动新建独立岗位。
            </p>
          )}
          {data.canResolve && (
            <Space style={{ marginTop: 12 }}>
              <select
                aria-label="合并到岗位"
                value={target}
                disabled={op.locked}
                onChange={(e) => setTarget(e.target.value)}
              >
                <option value="">请选择合并岗位</option>
                {data.candidates.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.name}（{p.id}）
                  </option>
                ))}
              </select>
              <Button
                disabled={op.locked || !target}
                onClick={() =>
                  void op.submit({ expected_version: data.version, target_id: target })
                }
              >
                并入选中岗位
              </Button>
              <Button
                disabled={op.locked}
                onClick={() => void op.submit({ expected_version: data.version })}
              >
                新建独立岗位
              </Button>
            </Space>
          )}
        </>
      ) : (
        <Alert
          type="info"
          message="岗位生成处理中，页面会自动更新；长时间未生成请联系管理员检查事件处理。"
        />
      )}
      {op.error && <Alert role="alert" type="error" message={op.error} />}
      {op.retry && (
        <Button onClick={() => void op.submit({ expected_version: data?.version ?? 1 })}>
          重试本次操作
        </Button>
      )}
      {op.conflict && <Button onClick={() => window.location.reload()}>刷新处理结果</Button>}
    </div>
  );
}
