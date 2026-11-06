import type { CandidateProfile } from './candidate-contracts';

export interface ConversationCommand {
  action:
    | 'send'
    | 'take_over'
    | 'hand_back'
    | 'issue_link'
    | 'revoke_links'
    | 'consent'
    | 'revoke'
    | 'do_not_contact'
    | 'ask_human'
    | 'correction_request'
    | 'deletion_request'
    | 'resolve_request';
  expected_version: number;
  content?: string;
  application_ids?: string[];
  reply_to_id?: string;
  request_id?: string;
}
export interface LiveConversation {
  id: string;
  version: number;
  candidate_version: number;
  mode: 'waiting_human' | 'hr';
  owner_id: string | null;
  consent: 'none' | 'granted' | 'revoked';
  do_not_contact: boolean;
  profile?: CandidateProfile;
  retention_until?: string;
  applications?: { id: string; position_name: string; status: string }[];
  requests: {
    id: string;
    kind: string;
    content: string;
    status: string;
    at: string;
    due_at: string;
    resolution?: string;
  }[];
  messages: {
    id: string;
    content: string;
    sender: 'candidate' | 'hr' | 'ai';
    channel: string;
    application_ids: string[];
    created_at: string;
    status?: 'sent' | 'queued' | 'cancelled';
    due_at?: string;
    reason?: string;
  }[];
}
export interface ConversationResult {
  conversation: LiveConversation;
  url?: string;
  expires_at?: string;
}
