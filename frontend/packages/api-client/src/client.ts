import type {
  AiActivity,
  Anomaly,
  Application,
  ApprovalNode,
  AutomationNode,
  Candidate,
  Conversation,
  DecisionCard,
  Evaluation,
  FunnelStage,
  Handoff,
  Interview,
  KbEntry,
  Level,
  Message,
  OperationLog,
  Position,
  PositionHealth,
  PrecheckItem,
  Profile,
  Requisition,
  RequisitionDraft,
  Resume,
  Slot,
  WorkbenchSummary,
} from '@recruiter/domain';

/** 写请求的公共参数：并发控制与幂等（实现文档第 9 节） */
export interface WriteOpts {
  idempotencyKey: string;
}

export interface CardResolution {
  option: string;
  expectedVersion: number;
  rejectReason?: string;
  /** 批量淘汰时勾选的应聘记录 */
  selected?: string[];
}

export interface BizInboxItem {
  id: string;
  kind: 'requisition_approval' | 'hire_decision' | 'recommendation' | 'feedback';
  title: string;
  detail: string;
  applicationId?: string;
  dueAt: string;
  done?: string;
  version?: number;
  nodeId?: string;
}

export interface RequisitionDetail extends Requisition {
  fields: Record<string, string>;
  chain: { id: string; name: string; approver_id: string; approver: string; note?: string }[];
  currentNode: number;
  creatorId: string;
  managerId: string;
  history: { action: string; actor_id: string; at: string; comment?: string; node_id?: string }[];
}

export interface RequisitionPage {
  items: Requisition[];
  total: number;
  page: number;
  size: number;
}

export interface HeadcountPlan {
  dept: string;
  year: number;
  version: number;
  planned: number;
  used: number;
  reserved: number;
  available: number;
  frozen: boolean;
  effective_from: string;
  updated_on: string;
  stale: boolean;
}

export interface HeadcountCommand {
  year: number;
  expected_version: number;
  planned: number;
  used: number;
  frozen: boolean;
  effective_from: string;
}

export interface CandidateBrief {
  applicationId: string;
  name: string;
  phoneMasked: string;
  positionName: string;
  headline: string;
  recommendation: string;
  confidence: number;
  highlights: { text: string; quote: string; ref: string }[];
  risks: string[];
  feedbacks: { interviewer: string; round: string; verdict: string; summary: string }[];
}

export interface PortalSession {
  candidateName: string;
  companyName: string;
  positionName: string;
  consent: 'none' | 'granted';
  progress: string;
}

/** 前端唯一的数据入口。真实环境走 HTTP，开发和演示走内存 mock，两者实现同一接口。 */
export interface ApiClient {
  headcountPlans(year: number): Promise<{ departments: string[]; items: HeadcountPlan[] }>;
  saveHeadcount(dept: string, command: HeadcountCommand, opts: WriteOpts): Promise<HeadcountPlan>;
  // 工作台
  workbenchSummary(): Promise<WorkbenchSummary>;
  listOpenCards(): Promise<DecisionCard[]>;
  resolveCard(id: string, body: CardResolution, opts: WriteOpts): Promise<DecisionCard>;
  batchResolve(ids: string[], option: string, opts: WriteOpts): Promise<DecisionCard[]>;
  aiActivity(): Promise<AiActivity[]>;
  undoAction(actionId: string, opts: WriteOpts): Promise<AiActivity>;
  correctAction(actionId: string, note: string, opts: WriteOpts): Promise<AiActivity>;
  positionHealth(): Promise<PositionHealth[]>;
  handoffs(): Promise<Handoff[]>;
  anomalies(): Promise<Anomaly[]>;

  // 候选人
  listCandidates(q?: string): Promise<(Candidate & { latest?: Application })[]>;
  getCandidate(id: string): Promise<Candidate>;
  listApplications(candidateId: string): Promise<Application[]>;
  getResume(candidateId: string): Promise<Resume>;
  getEvaluation(applicationId: string): Promise<Evaluation | null>;
  getConversation(candidateId: string): Promise<Conversation>;
  operationLogs(candidateId: string): Promise<OperationLog[]>;
  takeOver(candidateId: string, opts: WriteOpts): Promise<Conversation>;
  handBack(candidateId: string, opts: WriteOpts): Promise<Conversation>;
  sendAsHr(candidateId: string, text: string, opts: WriteOpts): Promise<Message>;
  revealContact(candidateId: string, opts: WriteOpts): Promise<{ phone: string; email: string }>;
  setKey(
    candidateId: string,
    isKey: boolean,
    expectedVersion: number,
    opts: WriteOpts,
  ): Promise<Candidate>;

  // 岗位
  listPositions(): Promise<Position[]>;
  getPosition(id: string): Promise<Position>;
  positionFunnel(id: string): Promise<FunnelStage[]>;
  positionApplications(
    id: string,
  ): Promise<(Application & { candidateName: string; confidence?: number })[]>;
  getProfile(positionId: string): Promise<Profile>;
  listKb(positionId: string): Promise<KbEntry[]>;
  transitionPosition(
    id: string,
    action: 'pause' | 'resume' | 'close',
    expectedVersion: number,
    opts: WriteOpts,
  ): Promise<Position>;

  // 招聘需求
  listRequisitions(): Promise<Requisition[]>;
  requisitionPage(page: number, size: number): Promise<RequisitionPage>;
  getRequisition(id: string): Promise<RequisitionDetail>;
  createRequisitionDraft(
    fields: Record<string, string>,
    opts: WriteOpts,
  ): Promise<RequisitionDetail>;
  updateRequisitionDraft(
    id: string,
    fields: Record<string, string>,
    version: number,
    opts: WriteOpts,
  ): Promise<RequisitionDetail>;
  submitRequisitionDraft(
    id: string,
    fields: Record<string, string>,
    version: number,
    opts: WriteOpts,
  ): Promise<RequisitionDetail>;
  withdrawRequisition(id: string, version: number, opts: WriteOpts): Promise<RequisitionDetail>;
  approveRequisition(
    id: string,
    nodeId: string,
    version: number,
    opts: WriteOpts,
  ): Promise<RequisitionDetail>;
  rejectRequisition(
    id: string,
    nodeId: string,
    version: number,
    reason: string,
    opts: WriteOpts,
  ): Promise<RequisitionDetail>;
  aiFillRequisition(text: string): Promise<RequisitionDraft>;
  precheckRequisition(fields: Record<string, string>): Promise<PrecheckItem[]>;
  approvalChain(fields: Record<string, string>): Promise<ApprovalNode[]>;
  submitRequisition(fields: Record<string, string>, opts: WriteOpts): Promise<Requisition>;

  // 面试
  listInterviews(): Promise<Interview[]>;

  // 设置
  automationNodes(): Promise<AutomationNode[]>;
  setAutomationLevel(key: string, level: Level, opts: WriteOpts): Promise<AutomationNode>;

  // 业务端
  bizInbox(): Promise<BizInboxItem[]>;
  bizAct(itemId: string, action: string, opts: WriteOpts): Promise<BizInboxItem>;
  candidateBrief(applicationId: string): Promise<CandidateBrief>;
  submitFeedback(
    applicationId: string,
    items: Record<string, string>,
    opts: WriteOpts,
  ): Promise<void>;

  // 候选人端
  portalSession(token: string): Promise<PortalSession>;
  portalConsent(token: string, granted: boolean, opts: WriteOpts): Promise<PortalSession>;
  portalMessages(token: string): Promise<Message[]>;
  portalSend(token: string, text: string, opts: WriteOpts): Promise<Message>;
  portalAskHuman(token: string, opts: WriteOpts): Promise<Message>;
  portalSlots(token: string): Promise<Slot[]>;
  portalPickSlot(token: string, slotId: string, opts: WriteOpts): Promise<Message>;
}

export interface ApiConfig {
  baseUrl: string;
  mock: boolean;
  getToken?: () => string | null;
}
