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
}
type Routes = { [K in keyof ApiClient]: (...args: Parameters<ApiClient[K]>) => Route };

const enc = encodeURIComponent;
const routes: Routes = {
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
  listPositions: () => ({ method: 'GET', path: '/hr/positions' }),
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
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = r.token ?? config.getToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (r.method !== 'GET')
      headers['Idempotency-Key'] = r.opts?.idempotencyKey ?? crypto.randomUUID();
    const res = await fetch(`${config.baseUrl}/api/v1${r.path}`, {
      method: r.method,
      headers,
      body: r.body === undefined ? undefined : JSON.stringify(r.body),
      credentials: 'include',
    });
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
