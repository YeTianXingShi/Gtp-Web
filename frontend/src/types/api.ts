// 与后端 API 契约对齐的类型定义
// 后端文件参考：gtpweb/blueprints/{auth,chat,conversation,admin,documents,bootstrap}.py

export interface User {
  username: string;
  is_admin: boolean;
}

export interface LoginResponse {
  ok: true;
  access_token: string;
  expires_in: number;
  user: User;
}

export interface ApiErrorResponse {
  ok: false;
  error: string;
}

export interface ApiOkResponse<T = unknown> {
  ok: true;
  [key: string]: unknown;
  data?: T;
}

export interface ModelOption {
  id: string;
  label: string;
  provider: "openai" | "google" | "claude";
  model_name: string;
  reasoning?: {
    enabled: boolean;
    effort: string;
    summary: string;
    effort_options: string[];
  } | null;
  thinking?: {
    enabled: boolean;
    include_thoughts: boolean;
    level: string;
    level_options: string[];
  } | null;
}

export interface ModelGroup {
  key: string;
  label: string;
  options: Pick<ModelOption, "id" | "label" | "provider" | "model_name">[];
}

export interface BootstrapData {
  user: User;
  models: {
    groups: ModelGroup[];
    options: ModelOption[];
    default: string;
  };
  attachments: {
    max_per_message: number;
    max_upload_mb: number;
    allowed_exts: string[];
  };
}

export interface Conversation {
  id: number;
  title: string;
  model: string;
  reasoning_effort: string;
  thinking_level: string;
  created_at: string;
  updated_at: string;
}

export interface MessageAttachment {
  id: number;
  file_name: string;
  mime_type: string;
  kind: "image" | "text" | "binary";
  is_image: boolean;
  preview_url: string | null;
  download_url: string;
  created_at: string;
}

export interface Message {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  reasoning: string;
  status: "complete" | "incomplete";
  created_at: string;
  attachments: MessageAttachment[];
}

export interface ConversationDetail {
  ok: true;
  model: string;
  reasoning_effort: string;
  thinking_level: string;
  messages: Message[];
}

export interface AdminUser {
  username: string;
  is_admin: boolean;
  enabled?: boolean;
  api_keys?: Record<string, string>;
}

export interface DashboardStats {
  ok: true;
  conversation_count: number;
  user_count: number;
  today_tokens: number;
  document_count: number;
}

export interface AuditLog {
  id: number;
  username: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: string;
  ip_address: string;
  created_at: string;
}

export interface DocumentMeta {
  id: number;
  title: string;
  category: string;
  file_name: string;
  file_size: number;
  mime_type: string;
  uploaded_by: string;
  created_at: string;
  updated_at: string;
}

export interface ConfigFileMeta {
  id: string;
  label: string;
  description: string;
  path: string;
  requires_restart: boolean;
  format: "json" | "jsonc" | "dotenv";
}
