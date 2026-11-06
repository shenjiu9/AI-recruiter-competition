// HTTP 实现：路径遵循 /api/v1/{端}/{资源}；POST 带 Idempotency-Key（实现文档第 9 节）
import type { ApiClient, ApiConfig, WriteOpts } from './client';
import { AppError } from './errors';

interface Route {
  method: 'GET' | 'POST' | 'PATCH';
  path: string;
  body?: unknown;
  opts?: WriteOpts;
  token?: string;
  unwrapItems?: boolean;
  binary?: boolean;
}
type Routes = { [K in keyof ApiClient]: (...args: Parameters<ApiClient[K]>) => Route };

const enc = encodeURIComponent;
const routes: Routes = {
  aiHealth: () => ({ method: 'GET', path: '/hr/ai-health' }),
  aiJobs: (page) => ({ method: 'GET', path: `/hr/ai-jobs?page=${page}` }),
  aiJob: (id) => ({ method: 'GET', path: `/hr/ai-jobs/${enc(id)}` }),
  startAiJob: (body, opts) => ({ method: 'POST', path: '/hr/ai-jobs', body, opts }),
  aiJobCommand: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/ai-jobs/${enc(id)}/actions`,
    body,
    opts,
  }),
  downloadHireHandoff: (id) => ({
    method: 'GET',
    path: `/hr/hiring/${enc(id)}/handoff.xlsx`,
    binary: true,
  }),
  liveHires: (page, filters = {}) => ({
    method: 'GET',
    path: `/hr/hiring?page=${page}&${new URLSearchParams(filters)}`,
  }),
  liveHire: (id) => ({ method: 'GET', path: `/hr/hiring/${enc(id)}` }),
  hireCommand: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/hiring/${enc(id)}/actions`,
    body,
    opts,
  }),
  liveWorkbench: () => ({ method: 'GET', path: '/hr/workbench-live' }),
  resolveLiveCard: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/decision-cards/${enc(id)}/resolve`,
    body,
    opts,
  }),
  liveAutomation: (filters) => ({
    method: 'GET',
    path: `/hr/automation-live?${new URLSearchParams(filters)}`,
  }),
  saveLiveAutomation: (body, opts) => ({ method: 'POST', path: '/hr/automation-live', body, opts }),
  liveInterviews: (page, filters = {}) => ({
    method: 'GET',
    path: `/hr/interviews?page=${page}&${new URLSearchParams(filters)}`,
  }),
  liveInterview: (id) => ({ method: 'GET', path: `/hr/interviews/${enc(id)}` }),
  interviewCommand: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/interviews/${enc(id)}/actions`,
    body,
    opts,
  }),
  interviewAvailability: () => ({ method: 'GET', path: '/biz/interview-availability' }),
  saveInterviewAvailability: (body, opts) => ({
    method: 'POST',
    path: '/biz/interview-availability',
    body,
    opts,
  }),
  candidateInterviews: (token) => ({ method: 'GET', path: '/candidate/interviews', token }),
  candidateInterviewCommand: (token, id, body, opts) => ({
    method: 'POST',
    path: `/candidate/interviews/${enc(id)}/actions`,
    token,
    body,
    opts,
  }),
  liveConversation: (id) => ({ method: 'GET', path: `/hr/candidates/${enc(id)}/conversation` }),
  conversationCommand: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/candidates/${enc(id)}/conversation`,
    body,
    opts,
  }),
  livePortal: (token) => ({ method: 'GET', path: '/candidate/session', token }),
  livePortalCommand: (token, body, opts) => ({
    method: 'POST',
    path: '/candidate/actions',
    token,
    body,
    opts,
  }),
  candidatePage: (page, filters = {}) => ({
    method: 'GET',
    path: `/hr/candidates?page=${page}&size=20&${new URLSearchParams(filters)}`,
  }),
  candidateRecord: (id) => ({ method: 'GET', path: `/hr/candidates/${enc(id)}` }),
  createCandidateRecord: (profile, opts) => ({
    method: 'POST',
    path: '/hr/candidates',
    body: { profile },
    opts,
  }),
  candidateRecordCommand: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/candidates/${enc(id)}/actions`,
    body,
    opts,
  }),
  revealCandidateContacts: (id) => ({ method: 'POST', path: `/hr/candidates/${enc(id)}/contacts` }),
  uploadCandidateResume: (file, cid, opts) => ({
    method: 'POST',
    path: `/hr/candidate-resumes?filename=${enc(file.name)}${cid ? `&candidate_id=${enc(cid)}` : ''}`,
    body: file,
    opts,
  }),
  downloadCandidateResume: (id, rid) => ({
    method: 'GET',
    path: `/hr/candidates/${enc(id)}/resumes/${enc(rid)}/file`,
    binary: true,
  }),
  attachCandidate: (body, opts) => ({ method: 'POST', path: '/hr/applications', body, opts }),
  livePositionApplications: (id) => ({
    method: 'GET',
    path: `/hr/positions/${enc(id)}/applications`,
  }),
  liveApplicationCommand: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/applications/${enc(id)}/actions`,
    body,
    opts,
  }),
  positionPage: (page, status, filters = {}) => ({
    method: 'GET',
    path: `/hr/positions?page=${page}&size=20${status ? `&status=${enc(status)}` : ''}&${new URLSearchParams(filters)}`,
  }),
  positionKnowledgePreview: (id, asked) => ({
    method: 'GET',
    path: `/hr/positions/${enc(id)}/knowledge-preview?asked=${asked}`,
  }),
  positionDetail: (id) => ({ method: 'GET', path: `/hr/positions/${enc(id)}` }),
  positionCommand: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/positions/${enc(id)}/actions`,
    body,
    opts,
  }),
  positionGeneration: (id) => ({ method: 'GET', path: `/hr/requisitions/${enc(id)}/position` }),
  resolvePositionGeneration: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/requisitions/${enc(id)}/position`,
    body,
    opts,
  }),
  formDepartments: (id) => ({
    method: 'GET',
    path: `/hr/requisition-form/departments${id ? `?requisition_id=${enc(id)}` : ''}`,
  }),
  formUsers: (dept, q, page, selected, id) => ({
    method: 'GET',
    path: `/hr/requisition-form/users?dept=${enc(dept)}&q=${enc(q)}&page=${page}&size=20${selected.map((uid) => `&selected=${enc(uid)}`).join('')}${id ? `&requisition_id=${enc(id)}` : ''}`,
  }),
  transferCandidates: (id, q, page) => ({
    method: 'GET',
    path: `/hr/requisitions/${enc(id)}/transfer-candidates?q=${enc(q)}&page=${page}&size=20`,
  }),
  transferRequisition: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/requisitions/${enc(id)}/transfer`,
    body,
    opts,
  }),
  requisitionNotifications: () => ({ method: 'GET', path: '/hr/requisition-notifications' }),
  organizationDepartments: () => ({ method: 'GET', path: '/admin/organization/departments' }),
  organizationUsers: (page, size, q = '') => ({
    method: 'GET',
    path: `/admin/organization/users?page=${page}&size=${size}&q=${enc(q)}`,
  }),
  savePermissions: (id, body, opts) => ({
    method: 'POST',
    path: `/admin/organization/users/${enc(id)}/permissions`,
    body,
    opts,
  }),
  saveApprovalPolicy: (dept, body, opts) => ({
    method: 'POST',
    path: `/admin/organization/approval?dept=${enc(dept)}`,
    body,
    opts,
  }),
  organizationHistory: (kind, id, page) => ({
    method: 'GET',
    path: `/admin/organization/history?kind=${kind}&object_id=${enc(id)}&page=${page}&size=20`,
  }),
  trialApproval: (dept, actor, hc, salary) => ({
    method: 'POST',
    path: `/admin/organization/trial?dept=${enc(dept)}`,
    body: { actor_id: actor, hc_request: hc, salary_over: salary },
  }),
  salaryBands: (page, size) => ({
    method: 'GET',
    path: `/admin/salary-bands?page=${page}&size=${size}`,
  }),
  salaryHistory: (id) => ({ method: 'GET', path: `/admin/salary-bands/${enc(id)}/history` }),
  saveSalaryBand: (body, opts) => ({ method: 'POST', path: '/admin/salary-bands', body, opts }),
  headcountPlans: (year) => ({ method: 'GET', path: `/admin/headcount?year=${year}` }),
  saveHeadcount: (dept, body, opts) => ({
    method: 'POST',
    path: `/admin/headcount?dept=${enc(dept)}`,
    body,
    opts,
  }),
  workbenchSummary: () => ({ method: 'GET', path: '/hr/workbench' }),
  listOpenCards: () => ({ method: 'GET', path: '/hr/cards?state=open' }),
  resolveCard: (id, body, opts) => ({
    method: 'POST',
    path: `/hr/cards/${enc(id)}/resolve`,
    body,
    opts,
  }),
  batchResolve: (ids, option, opts) => ({
    method: 'POST',
    path: '/hr/cards/batch-resolve',
    body: { ids, option },
    opts,
  }),
  aiActivity: () => ({ method: 'GET', path: '/hr/ai-activity' }),
  undoAction: (id, opts) => ({ method: 'POST', path: `/hr/ai-activity/${enc(id)}/undo`, opts }),
  correctAction: (id, note, opts) => ({
    method: 'POST',
    path: `/hr/ai-activity/${enc(id)}/correct`,
    body: { note },
    opts,
  }),
  positionHealth: () => ({ method: 'GET', path: '/hr/positions/health' }),
  handoffs: () => ({ method: 'GET', path: '/hr/conversations?mode=handoff' }),
  anomalies: () => ({ method: 'GET', path: '/hr/anomalies' }),
  listCandidates: (q) => ({ method: 'GET', path: `/hr/candidates${q ? `?q=${enc(q)}` : ''}` }),
  getCandidate: (id) => ({ method: 'GET', path: `/hr/candidates/${enc(id)}` }),
  listApplications: (id) => ({ method: 'GET', path: `/hr/candidates/${enc(id)}/applications` }),
  getResume: (id) => ({ method: 'GET', path: `/hr/candidates/${enc(id)}/resume` }),
  getEvaluation: (appId) => ({ method: 'GET', path: `/hr/applications/${enc(appId)}/evaluation` }),
  getConversation: (id) => ({ method: 'GET', path: `/hr/candidates/${enc(id)}/conversation` }),
  operationLogs: (id) => ({ method: 'GET', path: `/hr/candidates/${enc(id)}/logs` }),
  takeOver: (id, opts) => ({
    method: 'POST',
    path: `/hr/candidates/${enc(id)}/conversation/take-over`,
    opts,
  }),
  handBack: (id, opts) => ({
    method: 'POST',
    path: `/hr/candidates/${enc(id)}/conversation/hand-back`,
    opts,
  }),
  sendAsHr: (id, text, opts) => ({
    method: 'POST',
    path: `/hr/candidates/${enc(id)}/conversation/messages`,
    body: { text },
    opts,
  }),
  revealContact: (id, opts) => ({
    method: 'POST',
    path: `/hr/candidates/${enc(id)}/contact/reveal`,
    opts,
  }),
  setKey: (id, isKey, expectedVersion, opts) => ({
    method: 'POST',
    path: `/hr/candidates/${enc(id)}/key`,
    body: { is_key: isKey, expected_version: expectedVersion },
    opts,
  }),
  listPositions: () => ({ method: 'GET', path: '/hr/positions?size=100', unwrapItems: true }),
  getPosition: (id) => ({ method: 'GET', path: `/hr/positions/${enc(id)}` }),
  positionFunnel: (id) => ({ method: 'GET', path: `/hr/positions/${enc(id)}/funnel` }),
  positionApplications: (id) => ({ method: 'GET', path: `/hr/positions/${enc(id)}/applications` }),
  getProfile: (id) => ({ method: 'GET', path: `/hr/positions/${enc(id)}/profile` }),
  listKb: (id) => ({ method: 'GET', path: `/hr/positions/${enc(id)}/kb` }),
  transitionPosition: (id, action, expectedVersion, opts) => ({
    method: 'POST',
    path: `/hr/positions/${enc(id)}/${action}`,
    body: { expected_version: expectedVersion },
    opts,
  }),
  listRequisitions: () => ({ method: 'GET', path: '/hr/requisitions?size=100', unwrapItems: true }),
  requisitionPage: (page, size) => ({
    method: 'GET',
    path: `/hr/requisitions?page=${page}&size=${size}`,
  }),
  getRequisition: (id) => ({ method: 'GET', path: `/hr/requisitions/${enc(id)}` }),
  previewConfirmation: (id, fields, version) => ({
    method: 'POST',
    path: `/hr/requisitions/${enc(id)}/confirmation-preview`,
    body: { fields, expected_version: version },
  }),
  confirmRequisition: (id, fields, version, opts) => ({
    method: 'POST',
    path: `/hr/requisitions/${enc(id)}/confirm`,
    body: { fields, expected_version: version },
    opts,
  }),
  createRequisitionDraft: (fields, opts) => ({
    method: 'POST',
    path: '/hr/requisitions/drafts',
    body: fields,
    opts,
  }),
  updateRequisitionDraft: (id, fields, version, opts) => ({
    method: 'PATCH',
    path: `/hr/requisitions/${enc(id)}`,
    body: { fields, expected_version: version },
    opts,
  }),
  submitRequisitionDraft: (id, fields, version, opts) => ({
    method: 'POST',
    path: `/hr/requisitions/${enc(id)}/submit`,
    body: { fields, expected_version: version },
    opts,
  }),
  withdrawRequisition: (id, version, opts) => ({
    method: 'POST',
    path: `/hr/requisitions/${enc(id)}/withdraw`,
    body: { expected_version: version },
    opts,
  }),
  approveRequisition: (id, nodeId, version, opts) => ({
    method: 'POST',
    path: `/hr/requisitions/${enc(id)}/approve`,
    body: { node_id: nodeId, expected_version: version },
    opts,
  }),
  rejectRequisition: (id, nodeId, version, reason, opts) => ({
    method: 'POST',
    path: `/hr/requisitions/${enc(id)}/reject`,
    body: { node_id: nodeId, expected_version: version, reason },
    opts,
  }),
  aiFillRequisition: (text) => ({
    method: 'POST',
    path: '/hr/requisitions/ai-fill',
    body: { text },
  }),
  precheckRequisition: (fields) => ({
    method: 'POST',
    path: '/hr/requisitions/precheck',
    body: fields,
  }),
  approvalChain: (fields) => ({
    method: 'POST',
    path: '/hr/requisitions/approval-chain',
    body: fields,
  }),
  submitRequisition: (fields, opts) => ({
    method: 'POST',
    path: '/hr/requisitions',
    body: fields,
    opts,
  }),
  listInterviews: () => ({ method: 'GET', path: '/hr/interviews' }),
  automationNodes: () => ({ method: 'GET', path: '/admin/automation' }),
  setAutomationLevel: (key, level, opts) => ({
    method: 'PATCH',
    path: `/admin/automation/${enc(key)}`,
    body: { level },
    opts,
  }),
  bizInbox: () => ({ method: 'GET', path: '/biz/inbox' }),
  bizAct: (id, action, opts) => ({
    method: 'POST',
    path: `/biz/inbox/${enc(id)}/act`,
    body: { action },
    opts,
  }),
  candidateBrief: (appId) => ({ method: 'GET', path: `/biz/applications/${enc(appId)}/brief` }),
  submitFeedback: (appId, items, opts) => ({
    method: 'POST',
    path: `/biz/applications/${enc(appId)}/feedback`,
    body: items,
    opts,
  }),
  portalSession: (token) => ({ method: 'GET', path: '/candidate/session', token }),
  portalConsent: (token, granted, opts) => ({
    method: 'POST',
    path: '/candidate/consent',
    body: { granted },
    opts,
    token,
  }),
  portalMessages: (token) => ({ method: 'GET', path: '/candidate/messages', token }),
  portalSend: (token, text, opts) => ({
    method: 'POST',
    path: '/candidate/messages',
    body: { text },
    opts,
    token,
  }),
  portalAskHuman: (token, opts) => ({ method: 'POST', path: '/candidate/ask-human', opts, token }),
  portalSlots: (token) => ({ method: 'GET', path: '/candidate/slots', token }),
  portalPickSlot: (token, slotId, opts) => ({
    method: 'POST',
    path: '/candidate/slots/pick',
    body: { slot_id: slotId },
    opts,
    token,
  }),
};

export function createHttpClient(config: ApiConfig): ApiClient {
  async function call(r: Route): Promise<unknown> {
    const raw = r.body instanceof Blob;
    const headers: Record<string, string> = {
      'Content-Type': raw ? 'application/octet-stream' : 'application/json',
    };
    const token = r.token ?? config.getToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (r.method !== 'GET')
      headers['Idempotency-Key'] = r.opts?.idempotencyKey ?? crypto.randomUUID();
    const res = await fetch(`${config.baseUrl}/api/v1${r.path}`, {
      method: r.method,
      headers,
      body: raw ? (r.body as Blob) : r.body === undefined ? undefined : JSON.stringify(r.body),
      credentials: 'include',
    });
    if (r.binary && res.ok) return res.blob();
    const text = await res.text();
    let json: unknown = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      throw new AppError(
        'INVALID_RESPONSE',
        '服务返回了无法识别的内容，请稍后重试',
        res.status >= 400 ? res.status : 502,
      );
    }
    if (!res.ok) {
      if (res.status === 401 && !r.path.startsWith('/candidate/'))
        globalThis.dispatchEvent(new Event('recruiter:unauthorized'));
      const err = (
        json as {
          error?: {
            code: string;
            message: string;
            details?: Record<string, unknown>;
            trace_id?: string;
          };
        } | null
      )?.error;
      throw new AppError(
        err?.code ?? 'HTTP_ERROR',
        err?.message ?? `请求失败（${res.status}）`,
        res.status,
        err?.details,
        err?.trace_id,
      );
    }
    return r.unwrapItems ? (json as { items: unknown[] }).items : json;
  }
  const client = Object.fromEntries(
    Object.entries(routes).map(([name, build]) => [
      name,
      (...args: unknown[]) => call((build as (...a: unknown[]) => Route)(...args)),
    ]),
  );
  return client as unknown as ApiClient;
}
