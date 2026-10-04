#!/usr/bin/env bash
# Download a Hugging Face model into MODEL_ROOT as a plain directory (not HF cache layout).
#   MODEL_ROOT=/data/models scripts/download-model.sh Qwen/Qwen2.5-0.5B-Instruct [target-dir-name]
# Uses a throwaway python container, so nothing is installed on the host.
set -euo pipefail

REPO="${1:?usage: $0 <hf-repo-id> [target-dir-name]}"
NAME="${2:-${REPO##*/}}"
MODEL_ROOT="${MODEL_ROOT:-/data/models}"

[[ -d "$MODEL_ROOT" && -w "$MODEL_ROOT" ]] || { echo "MODEL_ROOT=$MODEL_ROOT missing or not writable"; exit 1; }

docker run --rm \
  -u "$(id -u):$(id -g)" \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -e HF_HOME=/tmp/hf \
  -v "$MODEL_ROOT:/models" \
  python:3.12-slim \
  bash -c "pip install -q --no-cache-dir --target /tmp/py 'huggingface_hub>=0.25' && \
           PYTHONPATH=/tmp/py python -c \"
from huggingface_hub import snapshot_download
p = snapshot_download(repo_id='$REPO', local_dir='/models/$NAME',
                      allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken','*.py','*.jinja'])
print('downloaded to', p)
\""

echo "done: $MODEL_ROOT/$NAME"
ls -la "$MODEL_ROOT/$NAME"
