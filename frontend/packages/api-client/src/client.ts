import type {
  LiveCandidate,
  CandidateProfile,
  CandidateCommand,
  IngestResult,
  AttachCommand,
  LiveApplication,
  ApplicationCommand,
} from './candidate-contracts';
export type * from './candidate-contracts';
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

export interface OrganizationUser {
  id: string;
  name: string;
  active: boolean;
  version: number;
  roles: string[];
  departments: string[];
  directory_roles: string[];
  directory_departments: string[];
}
export interface OrganizationDepartment {
  id: string;
  parent_id: string | null;
  version: number;
  approver_names?: Record<string, string | null>;
  policy: {
    manager_id: string;
    director_id: string;
    hrbp_id: string;
    hc_owner_id: string;
    hrd_id?: string | null;
  };
}
export interface PermissionCommand {
  expected_version: number;
  roles: string[];
  departments: string[];
}
export interface ApprovalPolicyCommand {
  expected_version: number;
  director_id: string;
  hrbp_id: string;
  hc_owner_id: string;
  hrd_id: string;
}
export interface OrganizationRevision {
  version: number;
  actor_id: string | null;
  at: string;
  data: OrganizationUser | OrganizationDepartment;
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
  ownerId: string;
  history: {
    action: string;
    actor_id: string;
    at: string;
    comment?: string;
    node_id?: string;
    from_id?: string;
    to_id?: string;
    from_name?: string;
    to_name?: string;
    changes?: Record<string, { before: string; after: string }>;
  }[];
}

export interface ConfirmationPreview {
  version: number;
  fields: Record<string, string>;
  changes: Record<string, { before: string; after: string }>;
  checks: PrecheckItem[];
  chain: RequisitionDetail['chain'];
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

export interface SalaryRevision {
  version: number;
  lower: number;
  upper: number;
  months: number;
  effective_from: string;
  updated_on: string;
}

export interface SalaryBand {
  id: string;
  series: string;
  grade: string;
  city: string;
  version: number;
  latest: SalaryRevision;
  active: SalaryRevision | null;
  stale: boolean;
}

export interface SalaryBandCommand {
  series: string;
  grade: string;
  city: string;
  lower: number;
  upper: number;
  months: number;
  effective_from: string;
  expected_version: number;
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
  candidatePage(
    page: number,
    filters?: Record<string, string>,
  ): Promise<{ items: LiveCandidate[]; total: number }>;
  candidateRecord(id: string): Promise<LiveCandidate>;
  createCandidateRecord(profile: CandidateProfile, opts: WriteOpts): Promise<IngestResult>;
  candidateRecordCommand(
    id: string,
    body: CandidateCommand,
    opts: WriteOpts,
  ): Promise<LiveCandidate | { deleted: true }>;
  revealCandidateContacts(id: string): Promise<{ phone: string; email: string }>;
  uploadCandidateResume(
    file: File,
    candidateId: string | undefined,
    opts: WriteOpts,
  ): Promise<IngestResult>;
  downloadCandidateResume(id: string, resumeId: string): Promise<Blob>;
  attachCandidate(body: AttachCommand, opts: WriteOpts): Promise<LiveApplication>;
  livePositionApplications(id: string): Promise<LiveApplication[]>;
  liveApplicationCommand(
    id: string,
    body: ApplicationCommand,
    opts: WriteOpts,
  ): Promise<LiveApplication>;
  positionPage(
    page: number,
    status?: string,
    filters?: Record<string, string>,
  ): Promise<{ items: LivePosition[]; total: number }>;
  positionKnowledgePreview(
    id: string,
    asked: boolean,
  ): Promise<{ entries: KnowledgeEntry[]; needsHuman: boolean }>;
  positionDetail(id: string): Promise<LivePosition>;
  positionCommand(id: string, command: PositionCommand, opts: WriteOpts): Promise<LivePosition>;
  positionGeneration(reqId: string): Promise<PositionGeneration>;
  resolvePositionGeneration(
    reqId: string,
    command: { expected_version: number; target_id?: string },
    opts: WriteOpts,
  ): Promise<PositionGeneration>;
  formDepartments(requisitionId?: string): Promise<{ id: string; parent_id: string | null }[]>;
  formUsers(
    dept: string,
    query: string,
    page: number,
    selected: string[],
    requisitionId?: string,
  ): Promise<{
    items: { id: string; name: string }[];
    total: number;
    selected: { id: string; name: string | null; available: boolean }[];
  }>;
  transferCandidates(
    id: string,
    query: string,
    page: number,
  ): Promise<{
    items: { id: string; name: string }[];
    total: number;
    version: number;
  }>;
  transferRequisition(
    id: string,
    body: {
      expected_version: number;
      node_id: string;
      target_id: string;
      reason: string;
    },
    opts: WriteOpts,
  ): Promise<RequisitionDetail>;
  requisitionNotifications(): Promise<
    {
      id: string;
      requisition_id: string;
      action: string;
      at: string;
      title: string;
    }[]
  >;
  organizationDepartments(): Promise<OrganizationDepartment[]>;
  organizationUsers(
    page: number,
    size: number,
    q?: string,
  ): Promise<{ items: OrganizationUser[]; total: number }>;
  savePermissions(
    id: string,
    command: PermissionCommand,
    opts: WriteOpts,
  ): Promise<OrganizationUser>;
  saveApprovalPolicy(
    dept: string,
    command: ApprovalPolicyCommand,
    opts: WriteOpts,
  ): Promise<OrganizationDepartment>;
  organizationHistory(
    kind: 'permissions' | 'approval',
    id: string,
    page: number,
  ): Promise<{ items: OrganizationRevision[]; total: number }>;
  trialApproval(
    dept: string,
    actor: string,
    hc: boolean,
    salary: boolean,
  ): Promise<{ version: number; chain: RequisitionDetail['chain'] }>;
  salaryBands(
    page: number,
    size: number,
  ): Promise<{ items: SalaryBand[]; total: number; page: number; size: number }>;
  salaryHistory(id: string): Promise<SalaryRevision[]>;
  saveSalaryBand(command: SalaryBandCommand, opts: WriteOpts): Promise<SalaryBand>;
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
  previewConfirmation(
    id: string,
    fields: Record<string, string>,
    version: number,
  ): Promise<ConfirmationPreview>;
  confirmRequisition(
    id: string,
    fields: Record<string, string>,
    version: number,
    opts: WriteOpts,
  ): Promise<RequisitionDetail>;
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

export interface LivePosition {
  candidateCounts: { total: number; active: number; hired: number; stages: Record<string, number> };
  id: string;
  version: number;
  name: string;
  dept: string;
  city: string;
  level: string;
  status: 'to_publish' | 'open' | 'paused' | 'closed';
  ownerHr: string;
  ownerId: string | null;
  hiringManager: string;
  managerId: string;
  planned: number;
  hired: number;
  expectedOnboard: string;
  confidential: boolean;
  requisitionIds: string[];
  profile: PositionProfile;
  activeProfile: PositionProfile | null;
  profiles: PositionProfile[];
  jd: PositionJd;
  jdVersions: PositionJd[];
  activeJd: PositionJd | null;
  jdApprovalRequired: boolean;
  knowledge: KnowledgeEntry[];
  sharedIds: string[];
  sharedMembers: { id: string; name: string }[];
  comments: {
    id: string;
    author: string;
    authorName: string;
    content: string;
    mentions: string[];
    at: string;
  }[];
  closeRequest: { requester: string; reason: string; at: string } | null;
  interviewPlans: { version: number; rounds: PositionInterviewRound[]; at: string }[];
  canLead: boolean;
  canCollaborate: boolean;
  canShare: boolean;
  canApproveJd: boolean;
  history: {
    action: string;
    actor: string;
    actorName: string;
    at: string;
    reason?: string;
    requisition_id?: string;
  }[];
  canEdit: boolean;
  canConfirm: boolean;
  canClose: boolean;
  canAssign: boolean;
}
export interface PositionCommand {
  expected_version: number;
  action:
    | 'assign'
    | 'save_profile'
    | 'confirm_profile'
    | 'publish'
    | 'pause'
    | 'resume'
    | 'close'
    | 'save_jd'
    | 'approve_jd'
    | 'reject_jd'
    | 'apply_jd'
    | 'configure_publish'
    | 'save_kb'
    | 'retire_kb'
    | 'share'
    | 'comment'
    | 'request_close'
    | 'confirm_close'
    | 'reject_close'
    | 'save_interview_plan'
    | 'amend_confirm_profile';
  reason?: string;
  handling?: 'continue' | 'freeze';
  owner_id?: string;
  must?: string;
  plus?: string;
  redflag?: string;
  jd?: string;
  must_ask?: string;
  plus_weights?: ('high' | 'medium' | 'low')[];
  jd_approval_required?: boolean;
  entry_id?: string;
  content?: string;
  source?: string;
  disclosure?: KnowledgeEntry['disclosure'];
  shared_ids?: string[];
  mentions?: string[];
  rounds?: PositionInterviewRound[];
}
export interface PositionGeneration {
  status: 'pending' | 'decision' | 'generated';
  version: number;
  position: { id: string; name: string; status: LivePosition['status'] } | null;
  candidates: { id: string; name: string }[];
  canResolve: boolean;
  dueAt?: string;
}

export interface PositionProfile {
  version: number;
  must: string;
  plus: string;
  redflag: string;
  must_ask: string;
  plus_weights: ('high' | 'medium' | 'low')[];
  jd: string;
  confirmedBy: string | null;
  source: string;
}
export interface PositionJd {
  version: number;
  content: string;
  author: string | null;
  approvedBy: string | null;
  status: 'draft' | 'approved' | 'rejected';
  reason?: string;
}
export interface KnowledgeEntry {
  id: string;
  version: number;
  previous_id: string | null;
  content: string;
  source: string;
  disclosure: 'proactive' | 'asked' | 'internal' | 'handoff';
  active: boolean;
}
export interface PositionInterviewRound {
  name: string;
  format: 'video' | 'onsite' | 'phone' | 'ai';
  duration: 15 | 30 | 45 | 60 | 90;
  interviewers: string[];
  rule: 'unanimous' | 'majority' | 'designated';
  decision_by?: string | null;
  criteria: string;
}
