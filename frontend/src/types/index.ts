export type UserRole = "admin" | "agent";

export interface CurrentUser {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
}

export type MailboxProvider = "nominalia" | "generic_imap";

export interface Mailbox {
  id: number;
  name: string;
  email_address: string;
  provider: MailboxProvider;
  imap_host: string;
  imap_port: number;
  imap_username: string;
  imap_use_ssl: boolean;
  inbox_folder: string;
  drafts_folder: string;
  is_active: boolean;
  last_checked_at: string | null;
  last_poll_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface MailboxFormValues {
  name: string;
  email_address: string;
  provider: MailboxProvider;
  imap_host: string;
  imap_port: number;
  imap_username: string;
  imap_password: string;
  imap_use_ssl: boolean;
  inbox_folder: string;
  drafts_folder: string;
}

export interface PromptTemplate {
  id: number;
  name: string;
  description: string | null;
  content: string;
  is_active: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentItem {
  id: number;
  filename: string;
  original_filename: string;
  content_type: string;
  is_active: boolean;
  text_length: number;
  created_at: string;
  updated_at: string;
}

export interface WebSource {
  id: number;
  name: string;
  root_url: string;
  max_pages: number;
  is_active: boolean;
  pages_crawled: number | null;
  text_length: number;
  last_fetched_at: string | null;
  last_fetch_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface WebSourceFormValues {
  name: string;
  root_url: string;
  max_pages: number;
}

export type ProcessingStatus =
  | "received"
  | "processing"
  | "draft_generated"
  | "draft_created_in_mailbox"
  | "failed"
  | "ignored";

export interface ProcessingListItem {
  email_message_id: number;
  mailbox_id: number;
  mailbox_name: string;
  subject: string;
  sender: string;
  received_at: string;
  status: ProcessingStatus;
  draft_id: number | null;
  error_message: string | null;
}

export type ProcessingLogStatus = "pending" | "processing" | "success" | "failed" | "retrying" | "ignored";
export type ProcessingStep =
  | "fetch_email"
  | "load_prompt"
  | "load_documents"
  | "build_context"
  | "call_llm"
  | "create_draft"
  | "finalize";

export interface ProcessingLogItem {
  id: number;
  status: ProcessingLogStatus;
  step: ProcessingStep;
  error_message: string | null;
  retry_count: number;
  started_at: string;
  finished_at: string | null;
}

export interface ProcessingDetail {
  email_message_id: number;
  mailbox_id: number;
  subject: string;
  sender: string;
  recipients: string;
  body_text: string | null;
  body_html: string | null;
  received_at: string;
  prompt_template_id: number | null;
  prompt_content_snapshot: string | null;
  documents_used: string[];
  web_sources_used: string[];
  thread_context: string | null;
  generated_body: string | null;
  draft_id: number | null;
  draft_status: string | null;
  final_status: ProcessingStatus;
  retry_count: number;
  logs: ProcessingLogItem[];
}

export type DraftStatus = "generated" | "created_in_mailbox" | "failed_to_create_in_mailbox" | "discarded";

export interface DraftListItem {
  id: number;
  mailbox_id: number;
  status: DraftStatus;
  created_in_mailbox: boolean;
  created_at: string;
}

export interface Draft {
  id: number;
  mailbox_id: number;
  email_message_id: number;
  prompt_template_id: number | null;
  generated_body: string;
  llm_provider: string;
  llm_model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost: number | null;
  status: DraftStatus;
  created_in_mailbox: boolean;
  mailbox_draft_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DashboardSummary {
  active_mailboxes: number;
  total_mailboxes: number;
  active_documents: number;
  total_documents: number;
  active_prompts: number;
  total_prompts: number;
  processed_emails: number;
  generated_drafts: number;
  recent_errors: ProcessingListItem[];
}
