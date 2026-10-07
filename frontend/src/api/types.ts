export type InstanceStatus = "CREATED" | "STARTING" | "LOADING" | "READY" | "STOPPING" | "STOPPED" | "ERROR";
export type GatewayState = "none" | "pending" | "registered" | "failed";
export type Health = "ok" | "attention" | "gateway_unreachable" | "gateway_db" | "runtime_error";

export interface Me {
  subject: string;
  roles: string[];
}

export interface MemoryStats {
  total_bytes: number;
  available_bytes: number;
  free_bytes: number;
  cached_bytes: number;
  used_bytes: number;
}

export interface DiskStats {
  path: string;
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
}

export interface GpuStats {
  name: string | null;
  driver: string | null;
  utilization_pct: number | null;
  temperature_c: number | null;
  power_w: number | null;
  process_bytes: number;
}

export interface SystemSummary {
  health: Health;
  capabilities: { memory: boolean; disk: boolean; gpu: boolean; docker: boolean };
  memory: MemoryStats | null;
  disk: DiskStats | null;
  gpu: GpuStats | null;
  gateway: { reachable: boolean; db_connected: boolean; version?: string; error?: string };
  counts: Record<InstanceStatus, number>;
  external_services: number;
  external_gpu_bytes: number;
}

export interface ExternalService {
  kind: "container" | "process";
  name: string;
  image: string | null;
  status: string | null;
  started_at: string | null;
  ports: number[];
  compose_project: string | null;
  pids: number[];
  gpu_bytes: number | null;
  hint_key: string;
}

export type SettingSource = "web" | "deploy" | "default";

export interface SettingValue<T> {
  value: T;
  source: SettingSource;
  default: T;
}

export interface AdvancedSettings {
  verbose_access_log: SettingValue<boolean>;
  hf_endpoint: SettingValue<string | null>;
  health_timeout_min: SettingValue<number>;
  timeout_range: [number, number];
  deploy: {
    profile: string;
    model_root: string;
    model_owner: string | null;
    hf_cache_dir: string | null;
    gateway_port: number;
    gateway_bind: string;
    gateway_local_only: boolean;
    vllm_image: string;
  };
}

export type AdvancedField = "verbose_access_log" | "hf_endpoint" | "health_timeout_min";

export interface AdvancedUpdate {
  verbose_access_log?: boolean;
  hf_endpoint?: string | null;
  health_timeout_min?: number;
  reset?: AdvancedField[];
}

export interface EndpointTestResult {
  ok: boolean;
  ms?: number;
  reason?: "timeout" | "network" | "http" | "not_hf";
  status?: number;
  url: string;
}

export interface InstanceMetrics {
  gpu_bytes: number | null;
  reserved_bytes: number | null;
  available: boolean;
}

export interface LogSource {
  id: string;
  kind: "service" | "platform";
  name: string;
  status: string | null;
}

export interface ModelDetails {
  model: ModelMeta;
  config: Record<string, unknown>;
  files: { name: string; size: number }[];
  presets: ResolvedPreset[];
}

export interface SystemInfo {
  version: string;
  profile: string;
  profile_description: string;
  vllm_image: string;
  timeouts?: { health_s: number; stop_s: number; slow_warning_s: number };
  docker: Record<string, unknown> | null;
  image: { id: string; repo_digests: string[] | null; architecture: string } | null;
  gateway: SystemSummary["gateway"];
}

export interface ModelMeta {
  id: string;
  source: string;
  locator: string;
  name: string;
  size_bytes: number | null;
  architecture: string | null;
  model_type: string | null;
  quantization: string | null;
  dtype: string | null;
  max_context: number | null;
  kv_bytes_per_token?: number | null;
  needs_remote_code: boolean;
  host_path: string;
  in_use_by: string[];
}

export interface ModelSourceInfo {
  id: string;
  type: string;
  path: string;
  model_count: number;
  available: boolean;
}

export interface Instance {
  id: string;
  display_name: string;
  served_model_name: string;
  model_id: string;
  preset: string;
  params: InstanceParams;
  autostart: boolean;
  autostart_order: number;
  status: InstanceStatus;
  phase: Phase | null;
  phase_started_at: string | null;
  last_error: InstanceError | null;
  gateway_state: GatewayState;
  created_at: string;
  updated_at: string;
  endpoint: { api_base: string; model: string };
  diagnostics?: {
    container_name: string | null;
    container_id: string | null;
    internal_url: string;
    image: string;
    gateway_model_id: string | null;
    command: string[] | null;
  } | null;
}

export type Phase = "queued" | "preparing" | "creating" | "loading" | "registering" | "ready";

export interface InstanceParams {
  max_model_len: number;
  gpu_memory_utilization: number;
  dtype: string;
  quantization: string;
  trust_remote_code: boolean;
  host_port: number | null;
  extra_args: string;
}

export interface Suggestion {
  action: "edit" | "apply_preset" | "navigate" | "logs" | "restart";
  label_key: string;
  patch?: Partial<InstanceParams> | null;
  preset?: string | null;
  target?: string | null;
  params?: Record<string, unknown>;
}

export interface InstanceError {
  code: string;
  severity: "error" | "warning";
  params: Record<string, unknown>;
  evidence: string[];
  suggestions: Suggestion[];
  occurred_at: string;
}

export interface Explanation {
  field: string;
  key: string;
  params: Record<string, unknown>;
}

export interface ResolvedPreset {
  id: string;
  label_key: string;
  description_key: string | null;
  recommended: boolean;
  params: InstanceParams;
  explanations: Explanation[];
}

export interface ParamField {
  name: keyof InstanceParams;
  level: "basic" | "advanced";
  type: "integer" | "number" | "string" | "boolean" | "select";
  widget: string;
  default: unknown;
  min: number | null;
  max: number | null;
  step: number | null;
  marks: number[];
  options: string[];
  unit: string | null;
  restart_required: boolean;
  label_key: string;
  help_key: string;
}

export type WarningLevel = "info" | "warning" | "blocking";

export interface PlanWarning {
  code: string;
  level: WarningLevel;
  params: Record<string, unknown>;
}

export interface MemoryEstimate {
  weights_bytes: number | null;
  kv_cache_bytes: number | null;
  overhead_bytes: number;
  total_bytes: number | null;
  budget_bytes: number | null;
  system_total_bytes: number | null;
  system_available_bytes: number | null;
  system_free_bytes: number | null;
  other_services_ratio: number;
}

export interface PlanInput {
  model_id: string;
  preset: string;
  params: Partial<InstanceParams>;
  display_name?: string | null;
  served_model_name?: string | null;
  autostart: boolean;
  autostart_order: number;
}

export interface Plan {
  model_id: string;
  preset: string;
  display_name: string;
  served_model_name: string;
  params: InstanceParams;
  autostart: boolean;
  autostart_order: number;
  estimate: MemoryEstimate;
  warnings: PlanWarning[];
  command: string[];
  blocking: boolean;
}

export interface InstanceEvent {
  id: number;
  type: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface LogLine {
  ts: string | null;
  text: string;
  annotation: string | null;
}

export interface TestResult {
  ok: boolean;
  latency_ms: number | null;
  reply_preview: string | null;
  error: string | null;
}

export type BudgetPeriod = "1d" | "7d" | "30d";
export type KeyExpiry = "7d" | "30d" | "90d" | "365d";

export interface KeyLimits {
  max_budget: number | null;
  budget_duration: BudgetPeriod | null;
  rpm_limit: number | null;
  tpm_limit: number | null;
  models: string[];
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  masked: string;
  status: "active" | "revoked" | "expired";
  created_at: string | null;
  last_active: string | null;
  expires_at: string | null;
  system: boolean;
  spend: number;
  limits: KeyLimits;
  budget_reset_at: string | null;
}

export interface CreateKeyBody extends KeyLimits {
  name: string;
  expires_in: KeyExpiry | null;
}

export interface UpdateKeyBody extends KeyLimits {
  name?: string;
}

export interface CreatedApiKey extends ApiKeyInfo {
  key: string;
}

export interface GatewayModel {
  model_name: string;
  gateway_model_id: string;
  instance_id: string | null;
  instance_name: string | null;
  instance_status: InstanceStatus | null;
  sync: "ok" | "orphan";
}

export type ApiBaseSource = "manual" | "deploy" | "auto";

export interface ApiBaseInfo {
  effective: string;
  source: ApiBaseSource;
  mode: "auto" | "manual" | null;
  manual: string | null;
  deploy: string | null;
  auto: string;
  warnings: string[];
}

export interface ConnectionInfo {
  api_base: string;
  source: ApiBaseSource;
  warnings: string[];
  models: string[];
}

export interface GatewayStatus {
  reachable: boolean;
  db_connected: boolean;
  version?: string | null;
  error?: string;
}

export interface DownloadPreview {
  repo_id: string;
  target_dir: string;
  exists: boolean;
  files: number;
  size_bytes: number;
  disk_free_bytes: number | null;
  has_config: boolean;
  has_weights: boolean;
  architecture: string | null;
  quantization: string | null;
  max_context: number | null;
  gated: boolean;
  warnings: string[];
  blocking: boolean;
}

export type DownloadStatus = "queued" | "downloading" | "completed" | "failed" | "cancelled";

export interface DownloadInfo {
  id: string;
  repo_id: string;
  revision: string | null;
  target_dir: string;
  status: DownloadStatus;
  bytes_total: number | null;
  bytes_done: number;
  files_total: number | null;
  progress: number | null;
  speed_bps: number | null;
  stalled_s: number | null;
  error: { code: string; message?: string } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  model_id: string | null;
}

export interface AutostartProgress {
  state: "idle" | "running" | "done" | "cancelled";
  queue: string[];
  current: string | null;
  results: Record<string, string>;
}

export type ProviderType = "openai" | "anthropic" | "gemini" | "openai_compatible";

export interface ProviderSpec {
  type: ProviderType;
  needs_api_base: boolean;
  api_key_required: boolean;
  test_model: string | null;
  catalog_provider: string | null;
  key_url: string | null;
}

export interface CloudProvider {
  id: string;
  type: ProviderType;
  name: string;
  api_base: string | null;
  masked_key: string | null;
  models: number;
}

export interface ConnTestResult {
  ok: boolean;
  model: string;
  error: string | null;
}

export interface CatalogModel {
  id: string;
  input_per_mtok: number | null;
  output_per_mtok: number | null;
  max_input_tokens: number | null;
}

export interface CloudModel {
  id: string;
  name: string;
  model: string;
  provider_id: string | null;
  provider_name: string | null;
  provider_type: ProviderType | null;
  input_per_mtok: number | null;
  output_per_mtok: number | null;
  custom_price: boolean;
}

export interface FallbackRule {
  model: string;
  targets: string[];
  active_alias: string | null;
}

export interface RoutingInfo {
  fallbacks: FallbackRule[];
  num_retries: number | null;
  models: string[];
}

export interface UsageMetrics {
  requests: number;
  successful: number;
  failed: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  spend: number;
}

export interface UsageRow {
  id: string;
  label: string;
  kind: "model" | "key" | "revoked" | "system" | "admin" | "unknown";
  metrics: UsageMetrics;
}

export interface UsageSummary {
  start: string;
  end: string;
  totals: UsageMetrics;
  days: { date: string; metrics: UsageMetrics }[];
  by_model: UsageRow[];
  by_key: UsageRow[];
}

export interface UsageLog {
  request_id: string;
  time: string | null;
  model: string | null;
  key_name: string | null;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  spend: number;
  duration_ms: number | null;
}

export interface UsageLogPage {
  items: UsageLog[];
  page: number;
  total_pages: number;
  total: number;
  capped: boolean;
}

export interface LocalPrice {
  input_per_mtok: number;
  output_per_mtok: number;
}