export interface CandidateProfile {
  name: string;
  phone: string;
  email: string;
  city: string;
  company: string;
  title: string;
  school: string;
  degree: string;
  graduation_year: number | null;
  years_exp: number | null;
  skills: string;
  experience: string;
  education: string;
  certificates: string;
  expected_city: string;
  expected_salary?: string;
}
export interface LiveResume {
  id: string;
  filename: string;
  at: string;
  status: 'ok' | 'partial' | 'failed';
  warning: string;
  profile: CandidateProfile;
  paragraphs: { id: string; text: string }[];
}
export interface LiveApplication {
  id: string;
  candidate_id?: string;
  candidate_name?: string;
  position_id: string;
  position_name: string;
  version: number;
  stage?: string;
  furthest_stage?: string;
  outcome: string | null;
  source?: string;
  started_at: string;
  reason?: string;
  restricted: boolean;
  can_edit?: boolean;
  can_rollback?: boolean;
  notice_status?: string;
  history?: {
    action: string;
    from_stage: string;
    to_stage: string;
    actor: string;
    at: string;
    reason: string;
  }[];
}
export interface LiveCandidate {
  id: string;
  version: number;
  profile: CandidateProfile;
  source: string;
  consent: 'none' | 'granted' | 'revoked';
  do_not_contact: boolean;
  key_candidate: boolean;
  tags: string[];
  can_edit: boolean;
  created_at: string;
  retention_until: string;
  resumes: LiveResume[];
  applications: LiveApplication[];
  similar: { id: string; name: string; version: number }[];
  merges: { id: string; at: string; reason: string }[];
  history: { action: string; actor: string; at: string }[];
}
export interface CandidateCommand {
  action: 'edit' | 'consent' | 'do_not_contact' | 'tags' | 'key' | 'merge' | 'unmerge' | 'erase';
  expected_version: number;
  profile?: CandidateProfile;
  resume_id?: string;
  reason?: string;
  granted?: boolean;
  evidence?: string;
  policy_version?: string;
  tags?: string[];
  key_candidate?: boolean;
  target_id?: string;
  target_version?: number;
}
export interface AttachCommand {
  candidate_id: string;
  position_id: string;
  source?: 'hr' | 'candidate';
  reason?: string;
  evidence?: string;
}
export interface ApplicationCommand {
  action: 'advance' | 'reject' | 'withdraw' | 'rollback' | 'undo_reject' | 'transfer';
  expected_version: number;
  reason?: string;
  reason_code?: '' | 'requirements' | 'experience' | 'skills' | 'salary' | 'location' | 'other';
  target_stage?: 'reach' | 'talking' | 'ai_eval' | 'interview' | 'manager_eval';
  target_position_id?: string;
  notify?: boolean;
}
export interface IngestResult {
  id: string;
  deduplicated: boolean;
  resume_id?: string;
  candidate: LiveCandidate;
}
