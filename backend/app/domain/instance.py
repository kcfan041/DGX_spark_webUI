from enum import StrEnum


class InstanceStatus(StrEnum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    LOADING = "LOADING"
    READY = "READY"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class InstancePhase(StrEnum):
    PREPARING = "preparing"
    CREATING = "creating"
    LOADING = "loading"
    REGISTERING = "registering"
    READY = "ready"


class GatewayState(StrEnum):
    NONE = "none"
    PENDING = "pending"
    REGISTERED = "registered"
    FAILED = "failed"


ACTIVE_STATUSES = frozenset({InstanceStatus.STARTING, InstanceStatus.LOADING, InstanceStatus.READY})
