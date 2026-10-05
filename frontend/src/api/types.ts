export type InstanceStatus = "CREATED" | "STARTING" | "LOADING" | "READY" | "STOPPING" | "STOPPED" | "ERROR";
export type GatewayState = "none" | "pending" | "registered" | "failed";
export type Health = "ok" | "attention" | "gateway_unreachable" | "runtime_error";

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
  processes: { pid: string; name: string; used_bytes: number | null }[];
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
}

export interface SystemInfo {
  version: string;
  profile: string;
  profile_description: string;
  vllm_image: string;
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
  params: Record<string, unknown>;
  autostart: boolean;
  autostart_order: number;
  status: InstanceStatus;
  phase: string | null;
  phase_started_at: string | null;
  last_error: Record<string, unknown> | null;
  gateway_state: GatewayState;
  created_at: string;
  updated_at: string;
}
