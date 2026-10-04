#!/usr/bin/env python
"""命令行入口。

用法
----
    python run.py --list                      列出全部规格
    python run.py --selftest                  用参考实现充当模型，跑通整条链路（无需 API Key）
    python run.py --all                       用 Agnes 模型跑全部规格
    python run.py --spec seq1011              只跑一个规格
    python run.py --all --max-attempts 6      调整修复预算
    python run.py --spec bcdadd -v            逐轮打印裁决过程（演示录像推荐）

环境变量
--------
    AGNES_API_KEY     Agnes 模型密钥（报名后由赛事官方群发放）
    AGNES_MODEL       模型 ID，默认 agnes-3.0-flash

密钥也可以放进文件（推荐用于录屏，避免画面里出现明文密钥）：
    ~/.agnes_key  →  仓库根/.agnes_key  →  仓库根/agnes.key
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from vlab.eda import EDABackend                    # noqa: E402
from vlab.specs import load_specs, project_root   # noqa: E402
from vlab.agnes import AgnesClient, ModelCallError  # noqa: E402
from vlab.loop import run_single_task, GoldenReferenceModel  # noqa: E402
from vlab.selfcheck import run_selfcheck, render_markdown   # noqa: E402


def cmd_list() -> int:
    specs = load_specs()
    print(f"{'id':<12}{'module':<13}{'类型':<14}{'难度':<9}数据位宽  激励策略")
    print("-" * 78)
    for s in specs:
        st = s.stimulus or {}
        mode = st.get("mode", "exhaustive")
        extra = st.get("order") or st.get("n") or ""
        print(f"{s.id:<12}{s.module:<13}{s.kind:<14}{s.difficulty:<9}"
              f"{s.data_input_width:<10}{mode}{' ' + str(extra) if extra != '' else ''}")
    print(f"\n共 {len(specs)} 条规格")
    return 0


def cmd_selftest() -> int:
    print("[1/2] 元验证：校准裁判本身")
    rows = run_selfcheck()
    out = project_root() / "runs"
    out.mkdir(exist_ok=True)
    (out / "selfcheck.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "selfcheck.md").write_text(render_markdown(rows), encoding="utf-8")
    bad = sum(1 for r in rows if not r["passed"])
    print(render_markdown(rows))
    print(f"裁判校准：{len(rows) - bad}/{len(rows)} 通过\n")

    print("[2/2] 链路自检：以参考实现替代模型走完整闭环")
    specs = load_specs()
    backend = EDABackend(timeout=60)
    model = GoldenReferenceModel()
    results = []
    for spec in specs:
        r = run_single_task(spec, model, backend,
                            project_root() / "runs" / "_selftest" / spec.id, max_attempts=1)
        flag = "OK " if r.ok else "NG "
        print(f"  {flag}{spec.id:<12} attempts={r.attempts} "
              f"{r.failure_class or 'PASS':<16} {r.seconds:.2f}s")
        results.append(r.to_dict())

    (out / "selftest_summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in results if r["ok"])
    print(f"\n链路自检：{ok}/{len(results)} 通过")
    return 0 if ok == len(results) else 1


# ------------------------------------------------------------------ 演示输出
# 失败类别 -> 给模型（也给观众）的一句话修复策略。
# 两套名字都兼容：judge 内部名 与 对外文档名。
REPAIR_HINT = {
    "SYNTAX": "把编译器报错行喂回模型：端口重复声明 / case 当表达式用 / 误用 SystemVerilog 关键字",
    "INTERFACE": "逐字比照规格端口表重写端口列表，重点核对方向与位宽",
    "PORT_MISMATCH": "逐字比照规格端口表重写端口列表，重点核对方向与位宽",
    "LATCH": "if / case 分支不完整 → 补 default 或在开头先赋默认值",
    "TIMEOUT": "疑似组合反馈环 → 检查是否存在无寄存器的自反馈路径",
    "COMB_LOOP": "疑似组合反馈环 → 检查是否存在无寄存器的自反馈路径",
    "RESET": "复位分支未覆盖全部寄存器 → 补齐复位赋值",
    "RESET_X": "复位分支未覆盖全部寄存器 → 补齐复位赋值",
    "TIMING_SHIFT": "逻辑正确但节拍偏移 ±N 拍 → 超前改寄存输出，滞后去掉多余一级流水",
    "VALUE_MISMATCH": "存在与参考不一致的输入向量 → 把反例向量表喂回模型",
    "EMPTY_OUTPUT": "模型未返回代码 → 重新生成并要求只输出 Verilog 代码块",
}


def _pad(text: str, width: int) -> str:
    """按**显示宽度**补齐（中日韩字符占两列），保证终端里竖线对齐。"""
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    return text + " " * max(1, width - w)


def render_attempt(idx: int, rec: dict) -> None:
    """把一轮裁决的过程打到终端 —— 演示录像的主要画面来源。"""
    W = 13  # 标签显示宽度
    print(f"\n    ┌─ 第 {idx + 1} 轮裁决 " + "─" * 50)
    labels = {"iverilog": "编译 iverilog", "vvp": "仿真 vvp", "yosys": "综合 yosys"}
    for t in rec.get("tools_called", []):
        name = labels.get(t.get("tool", ""), t.get("tool", "?"))
        ok = t.get("ok")
        tail = "" if ok else f"（返回码 {t.get('returncode')}）"
        print(f"    │ {_pad(name, W)} {'通过' if ok else '报错'}{tail}")
    cmp_ = rec.get("compare") or {}
    if cmp_:
        total = cmp_.get("total", 0)
        print(f"    │ {_pad('逐向量比对', W)} 一致 {cmp_.get('matched', 0)}/{total}，"
              f"不一致 {cmp_.get('mismatched', 0)}，通过率 {cmp_.get('pass_rate', 0):.2%}")
        fm = cmp_.get("first_mismatch")
        if fm:
            print(f"    │ {_pad('首个反例', W)} 第 {fm.get('idx')} 号：输入 {fm.get('in')}"
                  f" → 待测 {fm.get('dut')}，参考 {fm.get('ref')}")
        if cmp_.get("lag_matched"):
            print(f"    │ {_pad('平移重比对', W)} 平移 {-cmp_.get('best_lag', 0)} 拍后吻合 → 判定为节拍偏移")
    if rec.get("ok"):
        print(f"    └─ {_pad('裁决', W)} PASS —— {cmp_.get('total', 0)} 个向量全部与参考实现一致")
        return
    cls = rec.get("failure_class") or "UNKNOWN"
    print(f"    │ {_pad('失败类别', W)} {cls}")
    if rec.get("detail"):
        print(f"    │ {_pad('裁判说明', W)} {rec['detail']}")
    print(f"    └─ {_pad('修复策略', W)} {REPAIR_HINT.get(cls, '按类别针对性修订')}")


def cmd_run(args) -> int:
    model = AgnesClient(api_key=args.key,
                        journal_path=project_root() / "runs" / "model_journal.jsonl")

    try:
        model.chat("ping", purpose="health-check")
    except ModelCallError as exc:
        print(f"[错误] 无法调用 Agnes 模型：{exc}")
        print("      若还没有 API Key，可先运行 `python run.py --selftest` 验证本地链路。")
        return 2

    specs = load_specs()
    if args.spec:
        specs = [s for s in specs if s.id in args.spec]
        if not specs:
            print(f"[错误] 未找到规格：{args.spec}")
            return 2

    backend = EDABackend(timeout=60)
    out = project_root() / "runs"
    out.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    results = []

    print(f"开始评测：{len(specs)} 条规格，每条最多 {args.max_attempts} 次尝试\n")
    for spec in specs:
        st = spec.stimulus or {}
        print(f"  ══ 规格 {spec.id}（{'时序' if spec.kind.startswith('seq') else '组合'}"
              f"，{spec.difficulty}，激励 {st.get('mode', 'exhaustive')}"
              f"{' ' + str(st.get('order') or st.get('n') or '') if st.get('order') or st.get('n') else ''}）")

        def _cb(attempt: int, rec: dict, _spec=spec) -> None:
            if args.verbose:
                render_attempt(attempt, rec)

        r = run_single_task(spec, model, backend, out / stamp / spec.id,
                            max_attempts=args.max_attempts,
                            on_attempt=_cb if args.verbose else None)
        print()
        mark = "PASS" if r.ok else "FAIL"
        print(f"  [{mark}] {spec.id:<12} 首次通过={str(r.first_try_ok):<5} "
              f"尝试次数={r.attempts} 最后类别={r.failure_class or '-'} {r.seconds:.1f}s")
        print()
        results.append(r.to_dict())

    (out / f"run_{stamp}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    ok = sum(1 for r in results if r["ok"])
    first = sum(1 for r in results if r["first_try_ok"])
    print(f"\n汇总：{ok}/{len(results)} 通过，首次通过率 {first / max(1, len(results)):.1%}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="AGH 驱动的数字逻辑闭环验证引擎")
    ap.add_argument("--list", action="store_true", help="列出全部规格")
    ap.add_argument("--selftest", action="store_true", help="链路自检（无需 API Key）")
    ap.add_argument("--spec", nargs="*", help="指定规格 id，可多个")
    ap.add_argument("--all", action="store_true", help="跑全部规格")
    ap.add_argument("--key", default=None, help="Agnes API Key（默认读环境变量 AGNES_API_KEY）")
    ap.add_argument("--max-attempts", type=int, default=4, help="每条规格最多几轮修复")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="打印每一轮的完整裁决过程（推荐用于演示录像）")
    args = ap.parse_args()

    if args.list:
        return cmd_list()
    if args.selftest:
        return cmd_selftest()
    if args.all or args.spec:
        return cmd_run(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
