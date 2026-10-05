import type { Instance, InstanceStatus } from "@/api/types";

export type DisplayStatus = InstanceStatus | "READY_UNPUBLISHED";

export const STATUS_COLOR: Record<DisplayStatus, string> = {
  CREATED: "gray",
  STOPPED: "gray",
  STARTING: "blue",
  LOADING: "blue",
  READY: "green",
  READY_UNPUBLISHED: "yellow",
  STOPPING: "gray",
  ERROR: "red",
};

export function displayStatus(i: Pick<Instance, "status" | "gateway_state">): DisplayStatus {
  if (i.status === "READY" && i.gateway_state !== "registered") return "READY_UNPUBLISHED";
  return i.status;
}

export const isBusy = (s: InstanceStatus) => s === "STARTING" || s === "LOADING" || s === "STOPPING";
export const isStartable = (s: InstanceStatus) => s === "CREATED" || s === "STOPPED" || s === "ERROR";
export const isStoppable = (s: InstanceStatus) =>
  s === "STARTING" || s === "LOADING" || s === "READY" || s === "ERROR";
export const isLoading = (s: InstanceStatus) => s === "STARTING" || s === "LOADING";

export const STATUS_GROUPS = {
  all: null,
  ready: ["READY"],
  loading: ["STARTING", "LOADING", "STOPPING"],
  error: ["ERROR"],
  stopped: ["CREATED", "STOPPED"],
} as const satisfies Record<string, readonly InstanceStatus[] | null>;

export type StatusGroup = keyof typeof STATUS_GROUPS;
