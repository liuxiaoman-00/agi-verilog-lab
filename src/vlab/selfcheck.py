"""元验证（meta-verification）：先证明「裁判是可靠的」，再让裁判去评判模型。

这一步是整个作品可信度的地基。很多队伍的作品止步于「AI 输出了东西 + 我看着还行」，
而这里做的是反向的一件事：**刻意注入各类已知缺陷，验证验证器确实能抓住它们。**

三类内建用例：
  A. selfcheck  把参考实现改名后当候选交上去，必须全部 PASS（证明无冤假错案）
  B. seeded     注入已知缺陷，必须被判为**预先标注的那一类**（证明分类不跑偏）

先证明「裁判可靠」，裁判给出的结论才谈得上有说服力。
运行后产出 runs/selfcheck.md 与 runs/selfcheck.json。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from vlab.eda import EDABackend                       # noqa: E402
from vlab.specs import load_specs, golden_path, Spec  # noqa: E402
from vlab.harness import evaluate_once, EvalRecord    # noqa: E402


def _as_candidate(golden_text: str, spec: Spec) -> str:
    """把参考实现 `X_golden` 改名成候选实现 `X`，用于自校准。"""
    return re.sub(rf"\b{spec.golden_module}\b", spec.module, golden_text)


# --------------------------------------------------------------- 已知缺陷注入
# 每条都会被 evaluate_once 裁决，并与 expected 比对
SEEDED: list[dict] = [
    {
        "spec": "cmp4", "expect": "SYNTAX", "name": "漏写右括号",
        "note": "最基础的语法层拦截",
        "diff": lambda s: s.replace("assign gt = (a > b);", "assign gt = (a > b;"),
    },
    {
        "spec": "cmp4", "expect": "INTERFACE", "name": "端口位宽不符规格",
        "note": "b 从 [3:0] 被写成 [2:0]",
        "diff": lambda s: s.replace("input  wire [3:0] b,", "input  wire [2:0] b,"),
    },
    {
        "spec": "cmp4", "expect": "VALUE_MISMATCH", "name": "边界语义写错",
        "note": "gt 用 >= 而非 >，仅在 a==b 的边界暴露",
        "diff": lambda s: s.replace("assign gt = (a > b);", "assign gt = (a >= b);"),
    },
    {
        "spec": "add4", "expect": "LATCH", "name": "组合逻辑分支不完整",
        "note": "always @(*) 内 if 缺少 else，综合后推断出锁存器",
        "full": """module add4 (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output reg  [3:0] sum,
    output reg        cout
);
  wire [4:0] ext = a + b + cin;
  always @(*) begin
    if (cin) begin
      sum  = ext[3:0];
      cout = ext[4];
    end
  end
endmodule
""",
    },
    {
        "spec": "posdet", "expect": "TIMING_SHIFT", "name": "输出未寄存，早一拍",
        "note": "改成 assign 组合输出，比参考的寄存输出提前一个时钟周期",
        "full": """module posdet (
    input  wire clk,
    input  wire rst_n,
    input  wire x,
    output wire y
);
  reg x_d;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) x_d <= 1'b0;
    else        x_d <= x;
  end
  assign y = x & ~x_d;
endmodule
""",
    },
    {
        "spec": "sipo4", "expect": "VALUE_MISMATCH", "name": "移位方向反了",
        "note": "右移写成左移的反向顺序",
        "diff": lambda s: s.replace("q <= {q[2:0], din};", "q <= {din, q[3:1]};"),
    },
    {
        "spec": "dec38", "expect": "VALUE_MISMATCH", "name": "使能优先级错误",
        "note": "en=0 时忽略要求，仍输出译码结果",
        "diff": lambda s: s.replace("en ? (8'h01 << addr) : 8'h00", "8'h01 << addr"),
    },
]


def run_selfcheck(tool_home: Path | None = None, out_dir: Path | None = None) -> list[dict]:
    specs = {s.id: s for s in load_specs()}
    backend = EDABackend(tool_home=tool_home)
    work = (out_dir or ROOT / "runs") / "_selfcheck"
    rows: list[dict] = []

    # A. 参考实现自校准 —— 必须全部通过
    for sid, spec in specs.items():
        src = golden_path(spec).read_text(encoding="utf-8")
        rec = evaluate_once(spec, _as_candidate(src, spec), backend, work / sid, attempt=0)
        rows.append({
            "group": "selfcheck", "spec": sid, "case": "参考实现改名后自交",
            "expect": "PASS", "got": rec.failure_class or "PASS",
            "passed": rec.ok, "detail": rec.detail[:160],
            "vectors": rec.compare.get("total", 0),
            "cells": rec.cells.get("total", 0), "seconds": rec.seconds,
        })

    # B. 已知缺陷 —— 必须被判成预先标注的类别
    # 注意：工作路径必须是纯 ASCII。iverilog/pp 处理含非 ASCII 的路径会直接报
    # "Invalid argument / Preprocessor failed"，因此目录名一律用索引而非中文用例名。
    for i, case in enumerate(SEEDED):
        spec = specs[case["spec"]]
        workdir_name = f"seeded_{i:02d}_{spec.id}"
        src = _as_candidate(golden_path(spec).read_text(encoding="utf-8"), spec)
        if "full" in case:
            cand = case["full"]
        else:
            cand = case["diff"](src)
        if cand == src:
            rows.append({"group": "seeded", "spec": spec.id, "case": case["name"],
                         "expect": case["expect"], "got": "注入失败（源码未变化）",
                         "passed": False, "detail": "", "vectors": 0, "cells": 0, "seconds": 0})
            continue
        rec = evaluate_once(spec, cand, backend, work / workdir_name, attempt=0)
        got = rec.failure_class or "PASS"
        rows.append({
            "group": "seeded", "spec": spec.id, "case": case["name"],
            "expect": case["expect"], "got": got, "passed": got == case["expect"],
            "detail": rec.detail[:160], "vectors": rec.compare.get("total", 0),
            "cells": rec.cells.get("total", 0), "seconds": rec.seconds,
        })
    return rows


def render_markdown(rows: list[dict]) -> str:
    a = [r for r in rows if r["group"] == "selfcheck"]
    b = [r for r in rows if r["group"] == "seeded"]
    ok_a = sum(1 for r in a if r["passed"])
    ok_b = sum(1 for r in b if r["passed"])

    lines = [
        "# 元验证报告：先用已知缺陷校准裁判",
        "",
        f"- 参考实现自校准：{ok_a}/{len(a)} 通过",
        f"- 已知缺陷命中准确率：{ok_b}/{len(b)}",
        "",
        "## A. 参考实现自校准（应为 PASS）",
        "",
        "| 规格 | 向量数 | cell 数 | 结果 | 耗时(s) |",
        "|---|---:|---:|---|---:|",
    ]
    for r in a:
        lines.append(f"| {r['spec']} | {r['vectors']} | {r['cells']} | {r['got']} | {r['seconds']:.2f} |")
    lines += [
        "",
        "## B. 已知缺陷检出（应判为标注类别）",
        "",
        "| 规格 | 注入缺陷 | 期望类别 | 实际类别 | 判定 | 说明 |",
        "|---|---|---|---|---|---|",
    ]
    for r in b:
        flag = "OK" if r["passed"] else "MISS"
        lines.append(f"| {r['spec']} | {r['case']} | `{r['expect']}` | `{r['got']}` | {flag} | {r['detail'] or '-'} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    tool_home = ROOT.parent / "tools" / "oss-cad-suite"
    rows = run_selfcheck(tool_home=tool_home if tool_home.exists() else None)
    out = ROOT / "runs"
    out.mkdir(exist_ok=True)
    (out / "selfcheck.json").write_text(
        __import__("json").dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "selfcheck.md").write_text(render_markdown(rows), encoding="utf-8")
    print(render_markdown(rows))
    bad = sum(1 for r in rows if not r["passed"])
    print(f"\n[summary] {len(rows) - bad}/{len(rows)} 用例通过")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
