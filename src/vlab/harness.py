"""一次性执行引擎：把「候选实现 → 裁决」的全过程跑完并返回带完整留痕的记录。

这个模块是 AGH 会实际调用的那条**工具链**（在本地可直接 import，接入 AGH 时暴露为 MCP 工具）。
它刻意把所有副作用限制在 `workdir` 内，因此天然可并行、可复现、可审计。

留痕内容直接服务于赛事材料中的「运行证据」要求：
    tools_called  : 工具调用链（iverilog → vvp → yosys 及其参数与耗时）
    commands      : 每一条真实执行的命令
    classify      : 失败分类结论（正常 / 边界 / 失败三类样例由此产生）
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .eda import EDABackend, parse_cells, latch_count, flop_count
from .iface import parse_module, compare_interface
from .specs import Spec, golden_path
from . import verify as V


@dataclass
class EvalRecord:
    spec_id: str
    attempt: int
    ok: bool
    verdict: str
    failure_class: str | None = None
    detail: str = ""
    compare: dict = field(default_factory=dict)
    cells: dict = field(default_factory=dict)
    stimulus: dict = field(default_factory=dict)
    tools_called: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    workdir: str = ""
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "spec_id": self.spec_id, "attempt": self.attempt, "ok": self.ok,
            "verdict": self.verdict, "failure_class": self.failure_class,
            "detail": self.detail, "compare": self.compare, "cells": self.cells,
            "stimulus": self.stimulus, "tools_called": self.tools_called,
            "evidence": self.evidence, "workdir": self.workdir,
            "seconds": round(self.seconds, 3),
        }


def _write_stim(path: Path, vectors: list[int], width: int) -> None:
    lines = [format(v & ((1 << width) - 1), f"0{width}b") for v in vectors]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate_once(spec: Spec, candidate: str, backend: EDABackend, workdir: Path,
                  attempt: int = 0, max_lag: int = 3) -> EvalRecord:
    """对一份候选实现执行完整裁决流程。"""
    t0 = time.time()
    # 一律转成绝对路径：后续所有子进程都以 workdir 为 cwd，
    # 混用相对路径会导致文件二次拼接而找不到。
    wd = (Path(workdir).resolve() / f"attempt_{attempt}")
    if wd.exists():
        shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True, exist_ok=True)

    rec = EvalRecord(spec_id=spec.id, attempt=attempt, ok=False, verdict="",
                     workdir=str(wd))

    dut_file = wd / f"{spec.module}.v"
    golden_file = wd / f"{spec.module}_golden.v"
    tb_file = wd / "tb_vlab.v"
    stim_file = wd / "stim.txt"
    dut_file.write_text(candidate, encoding="utf-8")
    shutil.copyfile(golden_path(spec), golden_file)

    # ---- 激励构造（不依赖任何模型，纯确定性）
    in_width = max(1, spec.data_input_width)
    st = spec.stimulus or {}
    stim = V.generate_stimulus(
        width=in_width,
        mode=st.get("mode", "exhaustive"),
        n=int(st.get("n", 512)),
        seed=int(st.get("seed", 20260701)),
        spec_order=int(st.get("order", 6)),
    )
    rec.stimulus = {"mode": stim["mode"], "count": len(stim["vectors"]),
                    "width": in_width, "coverage": stim.get("coverage")}
    _write_stim(stim_file, stim["vectors"], in_width)

    # ---- 接口解析与比对
    info = parse_module(dut_file)
    iface = compare_interface(info, {
        "module": spec.module, "ports": spec.ports,
        "clock": spec.clock, "reset": spec.reset, "reset_active": spec.reset_active,
    })

    # ---- 渲染测试台
    tb_text = V.render_testbench(
        {"ports": spec.ports, "kind": spec.kind, "clock": spec.clock,
         "reset": spec.reset, "reset_active": spec.reset_active},
        dut_module=spec.module, ref_module=spec.golden_module,
        stimuli=stim["vectors"], in_width=in_width,
    )
    tb_file.write_text(tb_text, encoding="utf-8")

    # ---- 步骤 1：编译
    comp = backend.compile([tb_file, dut_file, golden_file], wd / "a.out", wd)
    rec.tools_called.append(comp.to_dict())
    rec.tools_called[-1]["command"] = " ".join(comp.command)

    # ---- 步骤 2：仿真（编译通过才有意义）
    trace, sim = V.Trace(), None
    if comp.ok:
        sim = backend.simulate(Path("a.out"), wd)
        rec.tools_called.append(sim.to_dict())
        rec.tools_called[-1]["command"] = " ".join(sim.command)
        trace = V.parse_trace(sim.stdout or "")

    # ---- 步骤 3：综合与结构侧检查
    cells: dict = {}
    syn = backend.synth([dut_file], spec.module, wd)
    rec.tools_called.append(syn.to_dict())
    rec.tools_called[-1]["command"] = " ".join(syn.command)
    if syn.ok:
        cells = parse_cells(syn.stdout or "")
    elif comp.ok:
        rec.evidence.append(f"yosys 未返回统计：{syn.tail(3)}")

    # ---- 步骤 4：比对与归因
    cmp_res = V.compare_traces(trace, max_lag=max_lag)
    rec.compare = cmp_res.to_dict()
    rec.cells = {
        "total": cells.get("__total__", 0),
        "latches": latch_count(cells),
        "flops": flop_count(cells),
        "raw": {k: v for k, v in cells.items() if k != "__total__"},
    }
    verdict = V.classify(comp, iface, trace, cmp_res, cells, spec.is_sequential)

    rec.ok = verdict.ok
    rec.verdict = verdict.explain()
    rec.failure_class = verdict.failure_class
    rec.detail = verdict.detail
    rec.evidence += verdict.evidence
    rec.seconds = time.time() - t0
    return rec


def dump_journal(records: list[EvalRecord], out: Path) -> None:
    """把完整裁决流水写成 JSONL，供评审复核。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
