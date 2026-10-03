#!/usr/bin/env python
"""命令行入口。

用法
----
    python run.py --list                      列出全部规格
    python run.py --selftest                  用参考实现充当模型，跑通整条链路（无需 API Key）
    python run.py --all                       用 Agnes 模型跑全部规格
    python run.py --spec seq1011              只跑一个规格
    python run.py --all --max-attempts 6      调整修复预算

环境变量
--------
    AGNES_API_KEY     Agnes 模型密钥（报名后由赛事官方群发放）
    AGNES_MODEL       模型 ID，默认 agnes-3.0-flash
"""
from __future__ import annotations

import argparse
import json
import sys
import time
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
        r = run_single_task(spec, model, backend, out / stamp / spec.id,
                            max_attempts=args.max_attempts)
        mark = "PASS" if r.ok else "FAIL"
        print(f"  [{mark}] {spec.id:<12} 首次通过={str(r.first_try_ok):<5} "
              f"尝试次数={r.attempts} 最后类别={r.failure_class or '-'} {r.seconds:.1f}s")
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
