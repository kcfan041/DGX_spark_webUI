"""Download a Hugging Face snapshot into a plain directory. Runs as a child process so it can be killed.

Usage: python -m app.workers.hf_download <json-args>
  args: {"repo_id", "revision", "local_dir", "allow_patterns", "endpoint"}
Token is read from the HF_TOKEN environment variable (never from argv).
Exit codes: 0 ok, 2 not found, 3 unauthorized / gated, 4 network, 1 other.
On failure, the last stderr line is a JSON object {"code": ..., "message": ...}.
"""

import json
import os
import sys


def classify(exc: BaseException) -> tuple[int, str]:
    from huggingface_hub.errors import (
        GatedRepoError,
        HfHubHTTPError,
        RepositoryNotFoundError,
        RevisionNotFoundError,
    )

    if isinstance(exc, GatedRepoError):
        return 3, "REPO_GATED"
    if isinstance(exc, RepositoryNotFoundError | RevisionNotFoundError):
        return 2, "REPO_NOT_FOUND"
    if isinstance(exc, HfHubHTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            return 3, "REPO_GATED"
        if status == 404:
            return 2, "REPO_NOT_FOUND"
        return 4, "NETWORK"
    if isinstance(exc, ConnectionError | TimeoutError):
        return 4, "NETWORK"
    name = type(exc).__name__
    if "Connection" in name or "Timeout" in name or "OfflineMode" in name:
        return 4, "NETWORK"
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return 1, "DISK_FULL"
    return 1, "UNKNOWN"


def main() -> int:
    args = json.loads(sys.argv[1])
    if args.get("endpoint"):
        os.environ["HF_ENDPOINT"] = args["endpoint"]
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=args["repo_id"],
            revision=args.get("revision") or None,
            local_dir=args["local_dir"],
            allow_patterns=args.get("allow_patterns") or None,
            token=os.environ.get("HF_TOKEN") or None,
            max_workers=4,
        )
    except BaseException as e:  # noqa: BLE001
        rc, code = classify(e)
        print(json.dumps({"code": code, "message": f"{type(e).__name__}: {e}"[:500]}), file=sys.stderr, flush=True)
        return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
