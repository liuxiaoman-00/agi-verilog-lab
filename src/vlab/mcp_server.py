"""MCP 服务：把裁决工具链暴露给 Agnes Harness（AGH）。

为什么要走 MCP 而不是写 AGH 原生插件
-----------------------------------
AGH 是 TypeScript 运行时，其原生插件要用 TS 编写并参与其包治理流程；
而本项目的领域逻辑全部在 Python（EDA 调用、轨迹解析、失败分类）。
AGH 明确支持 **MCP 连接**，于是把工具层做成一个标准 MCP 服务，
用 stdio 与 AGH 通信 —— 语言边界清晰，Python 侧可以独立测试与复用。

协议实现
--------
这里是**零依赖**的最小 MCP 服务：基于 JSON-RPC 2.0 over stdio，
实现 `initialize` / `tools/list` / `tools/call`，不引入任何第三方包，
因此评委拿到仓库后无需额外安装即可验证 AGH 接入路径。

启动：
    python -m vlab.mcp_server
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .eda import EDABackend
from .specs import load_specs, project_root
from .harness import evaluate_once
from . import verify as V

PROTOCOL_VERSION = "2024-11-05"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_specs",
        "description": "列出全部可用规格（题目）及其接口契约与激励策略。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "verify_candidate",
        "description": (
            "对一份 Verilog 候选实现执行完整裁决：编译 → 仿真 → 综合 → "
            "与参考实现逐向量比对 → 失败分类。返回裁决结论与证据。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec_id": {"type": "string", "description": "规格 id"},
                "source": {"type": "string", "description": "候选 Verilog 源码"},
                "attempt": {"type": "integer", "description": "第几次尝试，用于隔离工作目录"},
            },
            "required": ["spec_id", "source"],
        },
    },
    {
        "name": "describe_verdict",
        "description": "解释失败分类体系中每个类别的含义与推荐修复方向。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "stimulus_info",
        "description": "查询某条规格使用的激励策略、向量条数与覆盖率。",
        "inputSchema": {
            "type": "object",
            "properties": {"spec_id": {"type": "string"}},
            "required": ["spec_id"],
        },
    },
]


class MCPServer:
    def __init__(self) -> None:
        self._backend: EDABackend | None = None

    @property
    def backend(self) -> EDABackend:
        if self._backend is None:
            self._backend = EDABackend(timeout=60)
        return self._backend

    # ---------------------------------------------------------------- 工具实现
    def _list_specs(self) -> dict:
        return {"specs": [
            {"id": s.id, "title": s.title, "module": s.module, "kind": s.kind,
             "difficulty": s.difficulty, "ports": s.ports,
             "stimulus": s.stimulus, "data_width": s.data_input_width}
            for s in load_specs()
        ]}

    def _verify(self, args: dict) -> dict:
        spec_id = args["spec_id"]
        spec = next((s for s in load_specs() if s.id == spec_id), None)
        if spec is None:
            return {"error": f"未找到规格 {spec_id}"}
        attempt = int(args.get("attempt", 0))
        rec = evaluate_once(
            spec, args["source"], self.backend,
            project_root() / "runs" / "mcp" / spec_id, attempt=attempt,
        )
        return {"verdict": rec.verdict, "ok": rec.ok,
                "failure_class": rec.failure_class, "detail": rec.detail,
                "compare": rec.compare, "cells": rec.cells, "stimulus": rec.stimulus,
                "evidence": rec.evidence, "tools_called": rec.tools_called,
                "workdir": rec.workdir}

    def _stimulus_info(self, args: dict) -> dict:
        spec = next((s for s in load_specs() if s.id == args["spec_id"]), None)
        if spec is None:
            return {"error": "未找到规格"}
        in_width = max(1, spec.data_input_width)
        st = spec.stimulus or {}
        info = V.generate_stimulus(
            width=in_width, mode=st.get("mode", "exhaustive"),
            n=int(st.get("n", 512)), seed=int(st.get("seed", 20260701)),
            spec_order=int(st.get("order", 6)),
        )
        return {"spec_id": spec.id, "mode": info["mode"], "width": in_width,
                "vectors": len(info["vectors"]), "coverage": info["coverage"],
                "space": info["space"]}

    @staticmethod
    def _describe() -> dict:
        return {"taxonomy": V.FAILURE_TAXONOMY}

    # ---------------------------------------------------------------- 协议
    def handle(self, req: dict) -> dict | None:
        method = req.get("method")
        rid = req.get("id")
        params = req.get("params") or {}

        if method == "initialize":
            return _result(rid, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "vlab-verifier", "version": "0.1.0"},
            })
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return _result(rid, {"tools": TOOLS})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                if name == "list_specs":
                    payload = self._list_specs()
                elif name == "verify_candidate":
                    payload = self._verify(args)
                elif name == "describe_verdict":
                    payload = self._describe()
                elif name == "stimulus_info":
                    payload = self._stimulus_info(args)
                else:
                    return _error(rid, -32601, f"未知工具：{name}")
            except Exception as exc:                       # noqa: BLE001
                return _error(rid, -32000, f"{type(exc).__name__}: {exc}")
            return _result(rid, {"content": [
                {"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]})
        if method == "ping":
            return _result(rid, {})
        if rid is None:
            return None
        return _error(rid, -32601, f"未实现的方法：{method}")

    def serve(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()


def _result(rid, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": payload}


def _error(rid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def main() -> None:
    MCPServer().serve()


if __name__ == "__main__":
    main()
