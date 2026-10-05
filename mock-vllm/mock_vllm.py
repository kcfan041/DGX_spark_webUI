import argparse
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"ready": False, "served_name": "mock", "max_model_len": 4096}


def log(level: str, msg: str) -> None:
    ts = time.strftime("%m-%d %H:%M:%S")
    print(f"{level} {ts} [mock_vllm] {msg}", flush=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("mode", nargs="?", default="serve")
    p.add_argument("model", nargs="?", default="/models/mock")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--served-model-name", default=None)
    p.add_argument("--gpu-memory-utilization", type=float, default=0.9)
    p.add_argument("--max-model-len", type=int, default=4096)
    args, unknown = p.parse_known_args(argv)
    if unknown:
        log("WARNING", f"ignoring unsupported args: {unknown}")
    return args


def fail_generic() -> None:
    print("Traceback (most recent call last):", flush=True)
    print('  File "/usr/local/lib/python3.12/dist-packages/vllm/v1/engine/utils.py", line 1363', flush=True)
    print("RuntimeError: Engine core initialization failed. See root cause above. Failed core proc(s): {}",
          flush=True)
    os._exit(1)


def load_model(args: argparse.Namespace) -> None:
    config_path = os.path.join(args.model, "config.json")
    if not os.path.isfile(config_path):
        log("ERROR", f"No config.json found at {args.model}")
        os._exit(1)
    seconds = float(os.environ.get("MOCK_LOAD_SECONDS", "5"))
    steps = 5
    for i in range(1, steps + 1):
        time.sleep(seconds / steps)
        log("INFO", f"Loading safetensors checkpoint shards: {i * 100 // steps}% Completed | {i}/{steps}")
    fail = os.environ.get("MOCK_FAIL")
    if args.max_model_len == 1111 or fail == "oom":
        log("ERROR", "ValueError: No available memory for the cache blocks. "
                     "Try increasing `gpu_memory_utilization` when initializing the engine.")
        fail_generic()
    if args.max_model_len == 2222 or fail == "crash":
        fail_generic()
    STATE["ready"] = True
    log("INFO", "Application startup complete.")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *a) -> None:
        log("INFO", f'{self.client_address[0]} - "{self.command} {self.path}" {a[1] if len(a) > 1 else ""}')

    def _send(self, code: int, body: dict | None = None) -> None:
        data = json.dumps(body or {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200 if STATE["ready"] else 503)
        elif self.path == "/v1/models":
            if not STATE["ready"]:
                self._send(503)
                return
            self._send(200, {"object": "list", "data": [{
                "id": STATE["served_name"], "object": "model", "owned_by": "vllm",
                "max_model_len": STATE["max_model_len"]}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": "not found"})
            return
        if not STATE["ready"]:
            self._send(503)
            return
        if payload.get("model") != STATE["served_name"]:
            self._send(404, {"error": {"message": f"The model `{payload.get('model')}` does not exist."}})
            return
        last = (payload.get("messages") or [{}])[-1].get("content", "")
        log("INFO", "Avg prompt throughput: 1.0 tokens/s, Running: 1 reqs")
        self._send(200, {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": STATE["served_name"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": f"[mock] {last}"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        })


def main() -> None:
    args = parse_args(sys.argv[1:])
    STATE["served_name"] = args.served_model_name or args.model
    STATE["max_model_len"] = args.max_model_len
    log("INFO", f"mock vLLM serving {args.model} as {STATE['served_name']} on {args.host}:{args.port}")
    threading.Thread(target=load_model, args=(args,), daemon=True).start()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
