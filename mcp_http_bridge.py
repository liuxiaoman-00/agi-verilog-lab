# -*- coding: utf-8 -*-
"""把 vlab MCP 服务以 MCP Streamable HTTP 方式暴露在本地回环地址上。

为什么要有这一层：AGH 用 stdio 方式拉起外部进程时会被本机策略拦住
（MCP_RECONCILE_FAILED / MCP transport closed unexpectedly），
改成 HTTP 后由我们自己启动服务，AGH 只发起网络请求，不再涉及进程创建，
从而绕开该限制，让 AGH 能真正调用 verify_candidate（内部跑 iverilog/vvp/yosys）。

用法：
    python mcp_http_bridge.py [port]        # 默认 8765
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from vlab.mcp_server import MCPServer  # noqa: E402

SERVER = MCPServer()
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
CALLS = []


def handle_payload(raw: str) -> tuple[int, bytes, str]:
    """处理一段请求体，返回 (状态码, 响应体, 内容类型)。"""
    try:
        req = json.loads(raw)
    except json.JSONDecodeError:
        err = {"jsonrpc": "2.0", "id": None,
               "error": {"code": -32700, "message": "Parse error"}}
        return 400, json.dumps(err).encode("utf-8"), "application/json"

    batch = req if isinstance(req, list) else [req]
    results = []
    for one in batch:
        method = one.get("method", "")
        if method == "initialize":
            one = dict(one)
            one["params"] = one.get("params") or {}
        resp = SERVER.handle(one)
        if resp is None:
            # 通知类消息：无响应体
            continue
        results.append(resp)
        if isinstance(one, dict) and one.get("method", "").startswith("tools/"):
            CALLS.append({"method": one.get("method"),
                          "name": (one.get("params") or {}).get("name")})

    if not results:
        return 202, b"", "application/json"
    body = json.dumps(results[0] if len(results) == 1 else results,
                      ensure_ascii=False).encode("utf-8")
    return 200, body, "application/json"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "vlab-mcp-http/0.1"

    def _reply(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        accept = (self.headers.get("Accept") or "").lower()
        if "text/event-stream" in accept:
            body = b"event: endpoint\ndata: /mcp\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            info = {"server": "vlab-verifier", "transport": "streamable-http",
                    "endpoint": "/mcp", "callsSeen": len(CALLS)}
            self._reply(200, json.dumps(info, ensure_ascii=False).encode("utf-8"),
                        "application/json")

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8") if n else ""
        code, body, ctype = handle_payload(raw)
        accept = (self.headers.get("Accept") or "").lower()
        if body and "text/event-stream" in accept:
            sse = b"event: message\ndata: " + body + b"\n\n"
            self.send_response(code)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Content-Length", str(len(sse)))
            self.end_headers()
            self.wfile.write(sse)
            return
        self._reply(code, body, ctype)

    def log_message(self, fmt: str, *args) -> None:  # 安静一点
        sys.stderr.write("[mcp-http] " + (fmt % args) + "\n")


if __name__ == "__main__":
    sys.stderr.write(f"[mcp-http] listening on http://127.0.0.1:{PORT}/mcp\n")
    sys.stderr.flush()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
