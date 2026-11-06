import type { CandidateProfile } from './candidate-contracts';
import type { PositionInterviewRound } from './client';

export interface InterviewFeedback {
  author: string;
  scores: Record<string, number>;
  recommendation: string;
  strengths: string;
  concerns: string;
  next_focus: string;
  answers: Record<string, string>;
  submitted_at: string;
  remarks?: { text: string; at: string }[];
}
export interface LiveInterview {
  id: string;
  version: number;
  application_id: string;
  position_id: string;
  position_name: string;
  candidate_id?: string;
  candidate_name?: string;
  round_no: number;
  round_name: string;
  status: string;
  format: string;
  start: string | null;
  end: string | null;
  created_at: string;
  location: string;
  meeting_url: string;
  recording_consent: boolean;
  recording_enabled: boolean;
  integration_state: string;
  slots: { id: string; start: string; end: string; expires_at: string }[];
  requests: { actor?: string; reason: string; status: string }[];
  spec?: PositionInterviewRound;
  plan_version?: number;
  must_ask?: string;
  profile?: CandidateProfile;
  feedback?: Record<string, InterviewFeedback>;
  my_feedback?: InterviewFeedback;
  feedback_count?: number;
  result?: string;
  can_edit?: boolean;
  can_feedback?: boolean;
  interviewers?: { id: string; name: string }[];
  previous_rounds?: {
    round_no: number;
    result: string | null;
    feedback?: Record<string, InterviewFeedback>;
  }[];
  reminders?: { key: string; kind: string; hours?: number; user_id?: string; at: string }[];
}
export interface InterviewCommand {
  action:
    | 'configure'
    | 'offer'
    | 'book'
    | 'reschedule'
    | 'request_reschedule'
    | 'cancel'
    | 'complete'
    | 'no_show'
    | 'feedback'
    | 'remark'
    | 'retry_integration';
  expected_version: number;
  start?: string;
  slot_id?: string;
  reason?: string;
  location?: string;
  meeting_url?: string;
  recording_consent?: boolean;
  verified?: boolean;
  recused?: boolean;
  scores?: Record<string, number>;
  recommendation?: '' | 'strong_yes' | 'yes' | 'hold' | 'no';
  strengths?: string;
  concerns?: string;
  next_focus?: string;
  answers?: Record<string, string>;
}
export interface InterviewAvailability {
  version: number;
  weekdays: number[];
  start_hour: number;
  end_hour: number;
  daily_limit: number;
  weekly_limit: number;
  buffer_minutes: number;
}
