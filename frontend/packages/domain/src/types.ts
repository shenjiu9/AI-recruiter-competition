// 跨应用共享的领域类型。字段命名与后端契约（实现文档第 9 节、PRD 第 18 章）一致。

export type Id = string;
export type IsoTime = string;

/** 应聘记录的 6 个阶段（PRD 5.1） */
export type Stage = 'reach' | 'talking' | 'ai_eval' | 'interview' | 'manager_eval' | 'hired';
export type EndResult = 'rejected' | 'withdrawn' | 'offer_declined' | 'no_show_onboard' | 'position_closed';

/** 自动化等级：L1 只建议、L2 需确认、L3 已自动执行 */
export type Level = 1 | 2 | 3;
export type ConfidenceBand = 'high' | 'mid' | 'low';
export type HealthLevel = 'risk' | 'watch' | 'ok';

/** 表单字段来源（RQ-02） */
export type FieldSource =
  | 'description'
  | 'directory'
  | 'headcount'
  | 'history'
  | 'salary_table'
  | 'ai'
  | 'default'
  | 'edited';

export interface Versioned {
  id: Id;
  version: number;
}

export interface SalaryRange {
  low: number;
  high: number;
  unit: 'K/月';
  months?: number;
}

/** 证据引用：简历段落、会话消息、面评或规则 */
export interface EvidenceRef {
  kind: 'resume' | 'message' | 'feedback' | 'rule';
  ref: string; // R3 / m-88 / F1 / 规则名
  quote: string;
}

export interface Reason {
  text: string;
  evidence: EvidenceRef[];
}

export type CardType =
  | 'screen_result'
  | 'reject_confirm'
  | 'salary_over'
  | 'schedule_conflict'
  | 'possible_duplicate'
  | 'suggest_attach'
  | 'suggest_close'
  | 'profile_pending'
  | 'proxy_pending'
  | 'multi_hire';

export type CardState = 'open' | 'processing' | 'done' | 'void';

export interface CardOption {
  key: string;
  label: string;
  primary?: boolean;
  danger?: boolean;
  /** 选中后需要二次确认的后果描述 */
  confirm?: string;
}

export interface BatchItem {
  applicationId: Id;
  candidateName: string;
  reason: string;
  confidence: number;
}

export interface DecisionCard extends Versioned {
  type: CardType;
  title: string;
  object: { type: 'application' | 'position' | 'candidate' | 'requisition'; id: Id };
  positionName: string;
  candidateId?: Id;
  suggestion: string;
  confidence: number;
  lowReasons?: string[];
  level: Level;
  reasons: Reason[];
  options: CardOption[];
  dueAt: IsoTime;
  isKey?: boolean;
  state: CardState;
  voidReason?: string;
  resolvedNote?: string;
  batch?: BatchItem[];
}

export interface AiActivity {
  actionId: Id;
  at: IsoTime;
  text: string;
  level: Level;
  reversible: boolean;
  undoUntil?: IsoTime;
  reason: string;
  undone?: boolean;
  corrected?: boolean;
}

export interface PositionHealth {
  positionId: Id;
  name: string;
  openings: number;
  total: number;
  health: HealthLevel;
  why: string;
}

export interface Handoff {
  candidateId: Id;
  candidateName: string;
  positionName: string;
  reason: string;
  dueAt: IsoTime;
  lastMessage: string;
}

export interface Anomaly {
  id: Id;
  kind: string;
  text: string;
  link?: string;
}

export interface WorkbenchSummary {
  userName: string;
  pendingDecisions: number;
  dueToday: number;
  handoffs: number;
  aiActionsToday: number;
  hiredThisWeek: number;
  aiDegraded: boolean;
}

export interface Candidate extends Versioned {
  name: string;
  phoneMasked: string;
  emailMasked: string;
  city: string;
  currentCompany: string;
  currentTitle: string;
  years: number;
  education: string;
  isKey: boolean;
  consent: 'none' | 'granted';
  tags: string[];
}

export interface Application extends Versioned {
  candidateId: Id;
  positionId: Id;
  positionName: string;
  stage: Stage;
  subStatus: string;
  ended?: { result: EndResult; reason: string; at: IsoTime };
  startedAt: IsoTime;
  source: string;
}

export interface ResumeParagraph {
  ref: string; // R1…Rn
  text: string;
}

export interface Resume {
  candidateId: Id;
  fileName: string;
  paragraphs: ResumeParagraph[];
}

export type Verdict = 'meet' | 'not_meet' | 'unknown';
export type ProfileItemType = 'must' | 'plus' | 'redflag';

export interface EvaluationItem {
  id: string;
  type: ProfileItemType;
  text: string;
  weight?: '高' | '中' | '低';
  verdict: Verdict;
  evidence: EvidenceRef[];
  note: string;
  question?: string;
}

export interface Evaluation {
  applicationId: Id;
  conclusion: 'advance' | 'reject' | 'need_info' | 'hold';
  score: number;
  confidence: number;
  lowReasons: string[];
  items: EvaluationItem[];
  profileVersion: number;
  at: IsoTime;
}

export type Sender = 'candidate' | 'ai' | 'hr';

export interface Message {
  id: Id;
  sender: Sender;
  senderName?: string;
  text: string;
  at: IsoTime;
  kbRefs?: string[];
  draft?: boolean;
  status?: 'queued' | 'sent' | 'failed';
}

export type ConversationMode = 'ai' | 'handoff' | 'taken_over';

export interface Conversation {
  candidateId: Id;
  mode: ConversationMode;
  handoffReason?: string;
  handoffDueAt?: IsoTime;
  messages: Message[];
}

export interface OperationLog {
  at: IsoTime;
  actor: string;
  isAi: boolean;
  text: string;
}

export interface Position extends Versioned {
  name: string;
  dept: string;
  city: string;
  status: 'to_publish' | 'open' | 'paused' | 'closed';
  ownerHr: string;
  hiringManager: string;
  planned: number;
  hired: number;
  salary: SalaryRange;
  expectedOnboard: IsoTime;
  confidential: boolean;
  health: HealthLevel;
  requisitionIds: Id[];
}

export interface FunnelStage {
  stage: Stage;
  reached: number;
  current: number;
}

export interface ProfileItem {
  id: string;
  type: ProfileItemType | 'must_ask';
  text: string;
  weight?: '高' | '中' | '低';
}

export interface Profile {
  positionId: Id;
  version: number;
  confirmedBy?: string;
  items: ProfileItem[];
}

export interface KbEntry {
  id: string;
  scope: 'company' | 'position';
  title: string;
  content: string;
  disclosure: 'proactive' | 'on_ask' | 'internal' | 'human';
}

export interface Requisition extends Versioned {
  no: string;
  title: string;
  dept: string;
  type: 'new' | 'replace' | 'additional';
  headcount: number;
  initiator: string;
  mode: 'self' | 'proxy' | 'ai_draft';
  proxyBy?: string;
  status: 'draft' | 'in_approval' | 'approved' | 'rejected' | 'withdrawn';
  waitingFor?: string;
  waitingDays?: number;
  positionId?: Id;
  submittedAt?: IsoTime;
}

export interface FieldValue<T = string> {
  value: T;
  source: FieldSource;
  sourceDetail?: string;
}

export interface PendingDecision {
  field: string;
  question: string;
  options: string[];
}

export interface RequisitionDraft {
  fields: Record<string, FieldValue>;
  pending: PendingDecision[];
}

export interface PrecheckItem {
  key: string;
  label: string;
  status: 'pass' | 'warn' | 'block';
  detail: string;
}

export interface ApprovalNode {
  name: string;
  approver: string;
  note?: string;
}

export interface Interview extends Versioned {
  no: string;
  candidateId: Id;
  candidateName: string;
  positionName: string;
  round: number;
  roundName: string;
  form: '视频' | '现场' | 'AI 初面';
  start?: IsoTime;
  end?: IsoTime;
  interviewers: string[];
  status: 'to_schedule' | 'scheduling' | 'confirmed' | 'in_progress' | 'to_feedback' | 'done' | 'cancelled';
  feedbackDone: number;
  feedbackTotal: number;
  conflict?: string;
}

export interface AutomationNode {
  key: string;
  name: string;
  level: Level;
  allowed: Level[];
  cap?: string;
  note: string;
}

export interface Slot {
  id: Id;
  start: IsoTime;
  end: IsoTime;
}
