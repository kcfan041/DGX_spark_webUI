"""Stand-in for app.workers.hf_download used in tests. Behaviour is driven by repo_id."""

import json
import os
import sys
import time


def main() -> int:
    args = json.loads(sys.argv[1])
    repo, out = args["repo_id"], args["local_dir"]
    os.makedirs(out, exist_ok=True)
    if repo.endswith("/gated"):
        print(json.dumps({"code": "REPO_GATED", "message": "401"}), file=sys.stderr, flush=True)
        return 3
    if repo.endswith("/noconfig"):
        with open(os.path.join(out, "model.safetensors"), "wb") as f:
            f.write(b"0" * 10)
        return 0
    with open(os.path.join(out, "config.json"), "w") as f:
        json.dump({"architectures": ["FakeForCausalLM"], "max_position_embeddings": 4096}, f)
    os.makedirs(os.path.join(out, ".cache", "huggingface"), exist_ok=True)
    steps = 40 if repo.endswith("/slow") else 3
    for i in range(steps):
        with open(os.path.join(out, f"model-{i:05d}.safetensors"), "wb") as f:
            f.write(b"0" * 1000)
        time.sleep(0.05)
    print("token-seen=" + ("yes" if os.environ.get("HF_TOKEN") else "no"), file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
