#!/usr/bin/env python3
"""Run rust-analyzer over LSP on this crate and time Find All References on `decide`
(src/serve/idle.rs), the request an editor sends.

Usage: python3 find-refs.py [path-to-rust-analyzer]   (default: rust-analyzer on PATH)
Exit: 0 answered, 1 no answer within TIMEOUT seconds, 2 setup failure.
rust-analyzer runs in its own process group and is killed on every exit path.
"""
import atexit, json, os, signal, subprocess, sys, threading, time

TIMEOUT = 10
READY_TIMEOUT = 120
root = os.path.dirname(os.path.abspath(__file__))
rel = "src/serve/idle.rs"
text = open(os.path.join(root, rel)).read()
line = next(i for i, l in enumerate(text.splitlines()) if l.startswith("pub fn decide("))
col = len("pub fn ")

ra = sys.argv[1] if len(sys.argv) > 1 else "rust-analyzer"
p = subprocess.Popen([ra], cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, start_new_session=True)

def kill():
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

def bail(code):
    kill()
    os._exit(code)

atexit.register(kill)
for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, lambda *_: bail(130))

lock = threading.Lock()
pending = {}
ready = threading.Event()

def send(msg):
    body = json.dumps(msg).encode()
    with lock:
        p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        p.stdin.flush()

def reader():
    while True:
        hdr = b""
        while not hdr.endswith(b"\r\n\r\n"):
            c = p.stdout.read(1)
            if not c:
                print("rust-analyzer exited", flush=True)
                bail(2)
            hdr += c
        n = int([l for l in hdr.decode().split("\r\n") if l.lower().startswith("content-length")][0].split(":")[1])
        msg = json.loads(p.stdout.read(n))
        if "id" in msg and "method" in msg:  # server -> client request
            result = [{} for _ in msg["params"].get("items", [])] if msg["method"] == "workspace/configuration" else None
            send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
        elif "id" in msg:
            ev = pending.get(msg["id"])
            if ev:
                ev[1] = msg
                ev[0].set()
        elif msg.get("method") == "experimental/serverStatus" and msg["params"].get("quiescent"):
            ready.set()

threading.Thread(target=reader, daemon=True).start()
next_id = [0]

def request(method, params, timeout):
    next_id[0] += 1
    ev = [threading.Event(), None]
    pending[next_id[0]] = ev
    send({"jsonrpc": "2.0", "id": next_id[0], "method": method, "params": params})
    return ev[1] if ev[0].wait(timeout) else None

uri = "file://" + os.path.join(root, rel)
request("initialize", {
    "processId": os.getpid(), "rootUri": "file://" + root,
    "workspaceFolders": [{"uri": "file://" + root, "name": "repro"}],
    "capabilities": {"window": {"workDoneProgress": True}, "experimental": {"serverStatusNotification": True}},
}, READY_TIMEOUT)
send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
      "params": {"textDocument": {"uri": uri, "languageId": "rust", "version": 1, "text": text}}})
if not ready.wait(READY_TIMEOUT):
    print("rust-analyzer never finished loading", flush=True)
    bail(2)

start = time.time()
r = request("textDocument/references", {"textDocument": {"uri": uri}, "position": {"line": line, "character": col},
                                        "context": {"includeDeclaration": True}}, TIMEOUT)
if r is None:
    print(f"HANG: no answer to textDocument/references within {TIMEOUT}s", flush=True)
    bail(1)
print(f"OK: {len(r.get('result') or [])} references in {time.time() - start:.2f}s", flush=True)
bail(0)
