import { useRef, useState } from 'react';
import { Alert, Button, Descriptions, Input, Modal, Space, Spin, Table, Tag, Timeline } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  useApi,
  newIdempotencyKey,
  toAppError,
  type CandidateProfile,
  type LiveCandidate,
  type CandidateCommand,
} from '@recruiter/api-client';
import { PageHeader } from '../../../shared/PageHeader';
import { useLiveWrite } from '../../../shared/useLiveWrite';
import { AttachDialog, LiveApplicationTable, STAGE_LABEL } from '../../../shared/LiveApplications';
import { LiveConversation } from './LiveConversation';

const EMPTY: CandidateProfile = {
  name: '',
  phone: '',
  email: '',
  city: '',
  company: '',
  title: '',
  school: '',
  degree: '',
  graduation_year: null,
  years_exp: null,
  skills: '',
  experience: '',
  education: '',
  certificates: '',
  expected_city: '',
  expected_salary: '',
};
const LABELS: Record<keyof CandidateProfile, string> = {
  name: '姓名',
  phone: '手机号',
  email: '邮箱',
  city: '城市',
  company: '当前公司',
  title: '当前职位',
  school: '学校',
  degree: '最高学历',
  graduation_year: '毕业年份',
  years_exp: '工作年限',
  skills: '技能',
  experience: '工作经历',
  education: '教育经历',
  certificates: '证书',
  expected_city: '期望城市',
  expected_salary: '期望薪资',
};
const CONSENT = { none: '待授权', granted: '已授权', revoked: '已撤回授权' };
const ACTIONS: Record<CandidateCommand['action'], string> = {
  edit: '编辑基本信息',
  consent: '登记候选人授权',
  do_not_contact: '标记不再联系',
  tags: '编辑标签',
  key: '关键候选人设置',
  merge: '合并候选人档案',
  unmerge: '撤销合并',
  erase: '处理删除请求',
};

function ProfileForm({
  value,
  onChange,
  disabled,
}: {
  value: CandidateProfile;
  onChange: (p: CandidateProfile) => void;
  disabled: boolean;
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      {(Object.keys(LABELS) as (keyof CandidateProfile)[]).map((key) => (
        <label
          key={key}
          style={{
            gridColumn: ['skills', 'experience', 'education'].includes(key) ? '1 / -1' : undefined,
          }}
        >
          {LABELS[key]}
          {key === 'name' && ' *'}
          {key === 'graduation_year' || key === 'years_exp' ? (
            <Input
              aria-label={LABELS[key]}
              type="number"
              disabled={disabled}
              value={value[key] ?? ''}
              onChange={(e) =>
                onChange({ ...value, [key]: e.target.value ? Number(e.target.value) : null })
              }
            />
          ) : (
            <Input.TextArea
              aria-label={LABELS[key]}
              autoSize={{ minRows: 1, maxRows: 5 }}
              disabled={disabled}
              value={value[key] ?? ''}
              onChange={(e) => onChange({ ...value, [key]: e.target.value })}
            />
          )}
        </label>
      ))}
    </div>
  );
}

function CreateDialog({ onClose }: { onClose: () => void }) {
  const api = useApi();
  const nav = useNavigate();
  const cache = useQueryClient();
  const [profile, setProfile] = useState(EMPTY);
  const op = useLiveWrite(
    (body: CandidateProfile, opts) => api.createCandidateRecord(body, opts),
    (result) => {
      void cache.invalidateQueries();
      onClose();
      nav(`/candidates/${result.id}`);
    },
  );
  return (
    <Modal open title="新建候选人" footer={null} onCancel={onClose} width={700}>
      <ProfileForm value={profile} onChange={setProfile} disabled={op.locked} />
      <p>手动建档默认为待授权；联系方式相同会归入已有档案。</p>
      <Button
        type="primary"
        loading={op.busy}
        disabled={op.locked || !profile.name.trim()}
        onClick={() => void op.submit(profile)}
      >
        保存候选人
      </Button>
      {op.feedback}
    </Modal>
  );
}

interface UploadItem {
  file: File;
  key: string;
  status: 'ready' | 'done' | 'failed';
  result?: string;
  id?: string;
}
function UploadDialog({ candidateId, onClose }: { candidateId?: string; onClose: () => void }) {
  const api = useApi();
  const cache = useQueryClient();
  const [items, setItems] = useState<UploadItem[]>([]);
  const [busy, setBusy] = useState(false);
  const flight = useRef(false);
  const [error, setError] = useState('');
  const run = async () => {
    if (flight.current) return;
    flight.current = true;
    setBusy(true);
    for (const item of items.filter((i) => i.status !== 'done')) {
      try {
        const result = await api.uploadCandidateResume(item.file, candidateId, {
          idempotencyKey: item.key,
        });
        setItems((rows) =>
          rows.map((r) =>
            r.key === item.key
              ? {
                  ...r,
                  status: 'done',
                  id: result.id,
                  result: `${result.deduplicated ? '归入已有档案' : '新建档案'} · ${result.candidate.resumes.find((r) => r.id === result.resume_id)?.status === 'ok' ? '已提取，待核对' : '待人工补全'}`,
                }
              : r,
          ),
        );
      } catch (e) {
        setItems((rows) =>
          rows.map((r) =>
            r.key === item.key ? { ...r, status: 'failed', result: toAppError(e).message } : r,
          ),
        );
      }
    }
    void cache.invalidateQueries();
    setBusy(false);
    flight.current = false;
  };
  return (
    <Modal
      open
      title="上传简历"
      footer={null}
      onCancel={onClose}
      closable={!busy}
      maskClosable={!busy}
      width={700}
    >
      <p>PDF / Word / PNG / JPEG，单份不超过 20 MB，每批最多 200 份。扫描件和图片需人工补全。</p>
      <input
        aria-label="选择简历文件"
        type="file"
        multiple
        accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
        disabled={busy || items.length > 0}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length > 200 || files.some((f) => f.size > 20 * 1024 * 1024 || !f.size)) {
            setError('每批最多 200 份，文件必须非空且单份不超过 20 MB');
            return;
          }
          setError('');
          setItems(files.map((file) => ({ file, key: newIdempotencyKey(), status: 'ready' })));
        }}
      />
      {error && <Alert role="alert" type="error" message={error} />}
      <ul>
        {items.map((i) => (
          <li key={i.key}>
            {i.file.name} · {i.result ?? '待上传'}{' '}
            {i.id && (
              <Link to={`/candidates/${i.id}`} onClick={onClose}>
                查看档案
              </Link>
            )}
          </li>
        ))}
      </ul>
      <p>
        完成 {items.filter((i) => i.status === 'done').length} / {items.length}，失败{' '}
        {items.filter((i) => i.status === 'failed').length}
      </p>
      <Button
        type="primary"
        loading={busy}
        disabled={!items.length || items.every((i) => i.status === 'done')}
        onClick={() => void run()}
      >
        {items.some((i) => i.status === 'failed') ? '重试失败文件' : '开始上传'}
      </Button>
    </Modal>
  );
}

export function LiveCandidateList() {
  const api = useApi();
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get('page')) || 1);
  const query = params.get('query') ?? '';
  const state = params.get('state') ?? '';
  const city = params.get('city') ?? '';
  const [dialog, setDialog] = useState<'create' | 'upload'>();
  const q = useQuery({
    queryKey: ['live-candidates', page, query, state, city],
    queryFn: () => api.candidatePage(page, { query, state, city }),
    refetchInterval: 4000,
  });
  const filter = (key: string, value: string) =>
    setParams({ query, state, city, page: '1', [key]: value });
  return (
    <div>
      <PageHeader
        title="候选人"
        sub="同一候选人的简历与全部投递记录统一归档。"
        extra={
          <>
            <Button onClick={() => setDialog('upload')}>上传简历</Button>
            <Button type="primary" onClick={() => setDialog('create')}>
              新建候选人
            </Button>
          </>
        }
      />
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search
          aria-label="搜索候选人"
          key={query}
          defaultValue={query}
          placeholder="姓名、手机号、邮箱、公司、技能、标签"
          onSearch={(v) => filter('query', v)}
          style={{ width: 360 }}
        />
        <select
          aria-label="候选人状态"
          value={state}
          onChange={(e) => filter('state', e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="active">在流程中</option>
          <option value="idle">未在流程中</option>
          <option value="do_not_contact">不再联系</option>
        </select>
        <Input.Search
          aria-label="筛选城市"
          defaultValue={city}
          placeholder="城市"
          onSearch={(v) => filter('city', v)}
          style={{ width: 180 }}
        />
      </Space>
      {q.isError && <Alert role="alert" type="error" message={toAppError(q.error).message} />}
      <Table
        rowKey="id"
        loading={q.isLoading}
        dataSource={q.data?.items ?? []}
        pagination={{
          current: page,
          pageSize: 20,
          total: q.data?.total ?? 0,
          onChange: (p) => setParams({ query, state, city, page: String(p) }),
        }}
        columns={[
          {
            title: '候选人',
            render: (_, c: LiveCandidate) => (
              <>
                <Link to={`/candidates/${c.id}`}>{c.profile.name}</Link>
                <div>
                  {c.profile.company} · {c.profile.title}
                </div>
                <small>
                  {c.profile.city} {c.profile.phone}
                </small>
              </>
            ),
          },
          {
            title: '当前应聘',
            render: (_, c: LiveCandidate) =>
              c.applications
                .filter((a) => !a.outcome)
                .map((a) => (
                  <div key={a.id}>
                    {a.position_name} · {STAGE_LABEL[a.stage ?? ''] ?? '范围外'}
                  </div>
                )),
          },
          { title: '投递历史', render: (_, c: LiveCandidate) => `${c.applications.length} 次` },
          {
            title: '标签',
            render: (_, c: LiveCandidate) => c.tags.map((t) => <Tag key={t}>{t}</Tag>),
          },
          {
            title: '授权 / 联系状态',
            render: (_, c: LiveCandidate) => (
              <>
                {CONSENT[c.consent]}
                {c.do_not_contact && <Tag color="red">不再联系</Tag>}
                {c.key_candidate && <Tag>关键候选人</Tag>}
              </>
            ),
          },
        ]}
      />
      {dialog === 'create' && <CreateDialog onClose={() => setDialog(undefined)} />}
      {dialog === 'upload' && <UploadDialog onClose={() => setDialog(undefined)} />}
    </div>
  );
}

function CandidateAction({
  c,
  action,
  target,
  onClose,
}: {
  c: LiveCandidate;
  action: CandidateCommand['action'];
  target?: { id: string; version?: number };
  onClose: () => void;
}) {
  const api = useApi();
  const cache = useQueryClient();
  const nav = useNavigate();
  const [profile, setProfile] = useState<CandidateProfile>({ ...c.profile, phone: '', email: '' });
  const [ready, setReady] = useState(action !== 'edit');
  const [error, setError] = useState('');
  const [reason, setReason] = useState('');
  const [evidence, setEvidence] = useState('');
  const [granted, setGranted] = useState(true);
  const [tags, setTags] = useState(c.tags.join('，'));
  const [keyCandidate, setKeyCandidate] = useState(c.key_candidate);
  const [mergeQuery, setMergeQuery] = useState('');
  const [mergePage, setMergePage] = useState(1);
  const [selected, setSelected] = useState(target?.id ?? '');
  const options = useQuery({
    queryKey: ['merge-options', mergeQuery, mergePage],
    queryFn: () => api.candidatePage(mergePage, { query: mergeQuery }),
    enabled: action === 'merge' && !target,
  });
  const op = useLiveWrite<CandidateCommand, LiveCandidate | { deleted: true }>(
    (body, opts) => api.candidateRecordCommand(c.id, body, opts),
    (result) => {
      void cache.invalidateQueries();
      onClose();
      if ('deleted' in result) nav('/candidates');
    },
  );
  const loadContacts = async () => {
    try {
      const contacts = await api.revealCandidateContacts(c.id);
      setProfile((p) => ({ ...p, ...contacts }));
      setReady(true);
    } catch (e) {
      setError(toAppError(e).message);
    }
  };
  return (
    <Modal
      open
      title={ACTIONS[action]}
      onCancel={onClose}
      footer={null}
      width={action === 'edit' ? 700 : 560}
      maskClosable={!op.busy}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        {action === 'edit' &&
          (ready ? (
            <ProfileForm value={profile} onChange={setProfile} disabled={op.locked} />
          ) : (
            <Button onClick={() => void loadContacts()}>读取联系方式并开始编辑（记审计）</Button>
          ))}
        {action === 'consent' && (
          <>
            <p>仅登记候选人本人已表达的授权决定，请填写可追溯的证据。授权用途：招聘与 AI 评估。</p>
            <select
              aria-label="授权决定"
              value={String(granted)}
              disabled={op.locked}
              onChange={(e) => setGranted(e.target.value === 'true')}
            >
              <option value="true">已取得候选人同意</option>
              <option value="false">候选人撤回授权</option>
            </select>
            <Input
              aria-label="授权证据"
              placeholder="授权书编号、消息或记录引用"
              value={evidence}
              disabled={op.locked}
              onChange={(e) => setEvidence(e.target.value)}
            />
          </>
        )}
        {action === 'tags' && (
          <Input
            aria-label="候选人标签"
            placeholder="多个标签用逗号分隔"
            value={tags}
            disabled={op.locked}
            onChange={(e) => setTags(e.target.value)}
          />
        )}
        {action === 'key' && (
          <label>
            <input
              type="checkbox"
              checked={keyCandidate}
              disabled={op.locked}
              onChange={(e) => setKeyCandidate(e.target.checked)}
            />
            标记关键候选人（对外动作需要人工确认）
          </label>
        )}
        {action === 'merge' && (
          <>
            <p>
              保留当前主档案基本信息，合并全部简历和投递记录；7
              天内可撤销。同一岗位存在两条进行中记录时需先处理重复流程。
            </p>
            {target ? (
              <p>目标档案：{target.id}</p>
            ) : (
              <>
                <Input.Search
                  aria-label="搜索合并档案"
                  onSearch={(v) => {
                    setMergeQuery(v);
                    setMergePage(1);
                    setSelected('');
                  }}
                />
                <select
                  aria-label="合并目标档案"
                  value={selected}
                  disabled={op.locked}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  <option value="">请选择需合并的档案</option>
                  {options.data?.items
                    .filter((v) => v.id !== c.id)
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.profile.name} · {v.id.slice(-6)}
                      </option>
                    ))}
                </select>
                <Space>
                  <Button
                    disabled={mergePage === 1}
                    onClick={() => {
                      setMergePage((p) => p - 1);
                      setSelected('');
                    }}
                  >
                    上一页
                  </Button>
                  <Button
                    disabled={mergePage * 20 >= (options.data?.total ?? 0)}
                    onClick={() => {
                      setMergePage((p) => p + 1);
                      setSelected('');
                    }}
                  >
                    下一页
                  </Button>
                </Space>
              </>
            )}
          </>
        )}
        {action === 'erase' && (
          <Alert
            type="warning"
            message="将物理删除当前档案及其合并档案的个人信息、简历原件和应聘记录。此操作无法恢复。请核对候选人本人删除请求。"
          />
        )}
        {['consent', 'do_not_contact', 'merge', 'erase'].includes(action) && (
          <Input.TextArea
            aria-label="操作依据"
            placeholder="请填写原因或请求依据"
            disabled={op.locked}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        )}
        <Button
          type="primary"
          danger={action === 'erase'}
          loading={op.busy}
          disabled={op.locked || !ready}
          onClick={() =>
            void op.submit({
              action,
              expected_version: c.version,
              ...(action === 'edit' ? { profile, resume_id: target?.id } : {}),
              reason,
              evidence,
              granted,
              tags: tags
                .split(/[,，]/)
                .map((t) => t.trim())
                .filter(Boolean),
              key_candidate: keyCandidate,
              target_id: selected,
              target_version:
                target?.version ?? options.data?.items.find((v) => v.id === selected)?.version,
            })
          }
        >
          {action === 'erase' ? '确认执行删除' : '保存操作'}
        </Button>
        {error && <Alert role="alert" type="error" message={error} />}
        {op.feedback}
      </Space>
    </Modal>
  );
}

export function LiveCandidateDetail() {
  const { id = '' } = useParams();
  return <CandidateDetailContent key={id} id={id} />;
}

function CandidateDetailContent({ id }: { id: string }) {
  const api = useApi();
  const [action, setAction] = useState<{
    action: CandidateCommand['action'];
    target?: { id: string; version?: number };
  }>();
  const [attach, setAttach] = useState(false);
  const [upload, setUpload] = useState(false);
  const [contacts, setContacts] = useState<{ phone: string; email: string }>();
  const [error, setError] = useState('');
  const q = useQuery({
    queryKey: ['live-candidate', id],
    queryFn: () => api.candidateRecord(id),
    refetchInterval: 4000,
  });
  const reveal = async () => {
    try {
      setContacts(await api.revealCandidateContacts(id));
    } catch (e) {
      setError(toAppError(e).message);
    }
  };
  const download = async (rid: string, name: string) => {
    try {
      const blob = await api.downloadCandidateResume(id, rid);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = name;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(toAppError(e).message);
    }
  };
  if (q.isLoading) return <Spin />;
  if (q.isError || !q.data)
    return (
      <Alert
        role="alert"
        type="error"
        message={q.isError ? toAppError(q.error).message : '候选人不存在'}
      />
    );
  const c = q.data;
  return (
    <div>
      <Link to="/candidates">返回候选人</Link>
      <PageHeader
        title={c.profile.name}
        sub={
          [c.profile.company, c.profile.title, c.profile.city].filter(Boolean).join(' · ') ||
          '基本信息待补全'
        }
        extra={
          c.can_edit && (
            <>
              <Button
                onClick={() => setAttach(true)}
                disabled={c.do_not_contact || c.consent === 'revoked'}
              >
                挂到其他岗位
              </Button>
              <Button onClick={() => setUpload(true)}>上传简历版本</Button>
              <Link to={`/ai-jobs?component=A3&object=${encodeURIComponent(c.id)}`}>
                AI 提取复核
              </Link>
              <Link to={`/ai-jobs?component=A4&object=${encodeURIComponent(c.id)}`}>
                生成回复草稿
              </Link>
            </>
          )
        }
      />
      <Space wrap>
        <Tag>{CONSENT[c.consent]}</Tag>
        {c.do_not_contact && <Tag color="red">不再联系</Tag>}
        {c.key_candidate && <Tag color="purple">关键候选人</Tag>}
        {c.tags.map((t) => (
          <Tag key={t}>{t}</Tag>
        ))}
      </Space>
      <p>
        手机：{contacts?.phone || c.profile.phone || '待补全'} · 邮箱：
        {contacts?.email || c.profile.email || '待补全'}{' '}
        {c.can_edit && !contacts && <Button onClick={() => void reveal()}>查看完整联系方式</Button>}
      </p>
      {error && <Alert role="alert" type="error" message={error} />}
      {c.can_edit && (
        <Space wrap>
          {(['edit', 'consent', 'tags', 'key', 'merge', 'do_not_contact', 'erase'] as const).map(
            (a) => (
              <Button
                key={a}
                danger={a === 'erase'}
                disabled={a === 'do_not_contact' && c.do_not_contact}
                onClick={() => setAction({ action: a })}
              >
                {ACTIONS[a]}
              </Button>
            ),
          )}
        </Space>
      )}
      <h2>基本信息</h2>
      <Descriptions
        column={2}
        bordered
        items={(Object.keys(LABELS) as (keyof CandidateProfile)[])
          .filter((k) => !['name', 'phone', 'email'].includes(k))
          .map((k) => ({
            label: LABELS[k],
            children: (
              <span style={{ whiteSpace: 'pre-wrap' }}>
                {c.profile[k] === '' ? '未填写' : (c.profile[k] ?? '未填写')}
              </span>
            ),
          }))}
      />
      {c.similar?.length > 0 && (
        <Alert
          type="warning"
          message="发现姓名、学校、毕业年份相同的档案，请人工核对"
          description={c.similar.map((s) => (
            <p key={s.id}>
              <Link to={`/candidates/${s.id}`}>{s.name}</Link>{' '}
              <Button onClick={() => setAction({ action: 'merge', target: s })}>核对并合并</Button>
            </p>
          ))}
        />
      )}
      <h2>
        投递记录 {c.applications.filter((a) => !a.restricted).length} / {c.applications.length}
      </h2>
      <LiveApplicationTable rows={c.applications} />
      <p>
        <Link to={`/interviews?candidate_id=${encodeURIComponent(c.id)}`}>
          查看该候选人的面试安排与面评
        </Link>
        {' · '}
        <Link to={`/hiring?candidate_id=${encodeURIComponent(c.id)}`}>录用与结果回填</Link>
      </p>
      {c.can_edit && <LiveConversation key={c.id} id={c.id} applications={c.applications} />}
      {c.can_edit && (
        <>
          <h2>简历版本与解析核对</h2>
          {!c.resumes.length && <p>还没有上传简历，可先完善基本信息。</p>}
          {c.resumes.map((r) => (
            <article className="panel" key={r.id} style={{ padding: 16, marginBottom: 12 }}>
              <Space>
                <strong>{r.filename}</strong>
                <Tag>
                  {r.status === 'ok'
                    ? '已提取，待核对'
                    : r.status === 'partial'
                      ? '待人工补全'
                      : '解析失败'}
                </Tag>
                <span>{new Date(r.at).toLocaleString('zh-CN')}</span>
                <Button onClick={() => void download(r.id, r.filename)}>下载原件（记审计）</Button>
              </Space>
              <p>{r.warning}</p>
              <details>
                <summary>查看解析字段与段落</summary>
                <p>
                  解析姓名：{r.profile.name} · 手机：{r.profile.phone} · 邮箱：{r.profile.email}
                </p>
                <div style={{ maxHeight: 300, overflow: 'auto' }}>
                  {r.paragraphs.map((p) => (
                    <p key={p.id}>
                      <strong>{p.id}</strong> {p.text}
                    </p>
                  ))}
                </div>
              </details>
              <Button onClick={() => setAction({ action: 'edit', target: { id: r.id } })}>
                核对并修正资料
              </Button>
            </article>
          ))}
          {c.merges.length > 0 && (
            <>
              <h2>已合并档案</h2>
              {c.merges.map((m) => (
                <p key={m.id}>
                  {m.id} · {new Date(m.at).toLocaleString('zh-CN')} · {m.reason}{' '}
                  <Button onClick={() => setAction({ action: 'unmerge', target: m })}>
                    撤销合并
                  </Button>
                </p>
              ))}
            </>
          )}
          <h2>操作记录</h2>
          <Timeline
            items={c.history.map((h, i) => ({
              key: i,
              children: `${ACTIONS[h.action as CandidateCommand['action']] ?? h.action} · ${h.actor} · ${new Date(h.at).toLocaleString('zh-CN')}`,
            }))}
          />
        </>
      )}
      {action && (
        <CandidateAction
          c={c}
          {...action}
          onClose={() => {
            setAction(undefined);
            setContacts(undefined);
          }}
        />
      )}
      {attach && <AttachDialog candidateId={c.id} onClose={() => setAttach(false)} />}
      {upload && <UploadDialog candidateId={c.id} onClose={() => setUpload(false)} />}
    </div>
  );
}
