import type { InterviewFeedback } from './interview-contracts';
import type { PositionInterviewRound } from './client';

export interface HireFacts {
  salary_k?: number;
  salary_months?: number;
  expected_start: string;
  offer_owner: string;
  evidence?: string;
  salary_over: boolean;
}
export interface LiveHire {
  department: string;
  id: string;
  version: number;
  application_id: string;
  candidate_id: string;
  position_id: string;
  candidate_name: string;
  position_name: string;
  status: string;
  remaining: number;
  due_at: string;
  review_stamp: string;
  facts: HireFacts | null;
  chain: { role: string; name: string; user_id: string; status: string; reason?: string }[];
  feedback: {
    id: string;
    round_no: number;
    round_name: string;
    result: string;
    feedback: Record<string, InterviewFeedback>;
  }[];
  averages: Record<string, number>;
  can_prepare: boolean;
  can_decide: boolean;
  can_approve: boolean;
  can_withdraw: boolean;
  can_handover: boolean;
  can_result: boolean;
  reminders: { key: string; kind: string; at: string }[];
  result: { value: string; reason: string; expected_start: string | null } | null;
  handoff: {
    candidate: Record<string, string>;
    position: Record<string, string>;
    facts: HireFacts;
    delivery: string;
    evidence?: string;
    generated_at: string;
  } | null;
  history: { action: string; actor?: string; at: string; reason?: string }[];
}
export interface HireCommand {
  action: 'prepare' | 'decide' | 'approve' | 'reject' | 'withdraw' | 'handover' | 'result';
  expected_version: number;
  verified?: boolean;
  review_stamp?: string;
  reason?: string;
  decision?: 'hire' | 'reject' | 'extra_round';
  salary_k?: number;
  salary_months?: number;
  evidence?: string;
  offer_owner?: string;
  expected_start?: string;
  extra_round?: PositionInterviewRound;
  result?: 'accepted' | 'declined' | 'joined' | 'no_show';
}
export interface LiveCard {
  id: string;
  version: number;
  kind: string;
  title: string;
  state: string;
  href: string;
  options: string[];
  due_at: string | null;
  overdue?: boolean;
}
export interface CardCommand {
  expected_version: number;
  option: 'dismiss' | 'reject' | 'terminate' | 'keep';
  reason: string;
}
export interface LiveWorkbench {
  counts: Record<string, number>;
  cards: LiveCard[];
  hires: LiveHire[];
  ai_enabled: boolean;
  positions: {
    id: string;
    name: string;
    status: string;
    planned: number;
    hired: number;
    remaining: number;
    stages: Record<string, number>;
  }[];
}
export interface AutomationConfig {
  id: string;
  version: number;
  levels: Record<string, number>;
  mode: 'normal' | 'shadow' | 'manual';
  components: Record<string, boolean>;
  low_threshold: number;
  high_threshold: number;
  approval_nodes: ('director' | 'hrbp')[];
  hrd_grade: number;
  nodes: { key: string; name: string; min: number; max: number }[];
  history: { version: number; at: string; actor: string }[];
}
export interface AutomationCommand {
  expected_version: number;
  scope: string;
  target: string;
  dept: string;
  levels?: Record<string, number>;
  mode?: AutomationConfig['mode'];
  components?: Record<string, boolean>;
  low_threshold?: number;
  high_threshold?: number;
  approval_nodes?: AutomationConfig['approval_nodes'];
  hrd_grade?: number;
  restore_version?: number;
}
