# -*- coding: utf-8 -*-
"""用本项目自己的裁判，独立复验 AGH 在真实会话中生成的 Verilog。

这一步把两套证据串起来：AGH 负责「生成」，本项目裁判负责「判定」，
判定标准与生成过程完全独立（编译器 + 仿真器 + 综合器 + 人工参考实现）。

用法：python tools_verify_agh_output.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from vlab.eda import EDABackend          # noqa: E402
from vlab.harness import evaluate_once   # noqa: E402
from vlab.specs import get_spec, load_specs  # noqa: E402

SRC = HERE / "agh_demo_cmp4.v"
OUT = HERE / "evidence" / "agh_session" / "05_AGH产出_经本项目裁判复验.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

specs = load_specs()
spec = get_spec(specs, "cmp4")
if spec is None:
    print("找不到 cmp4 规格")
    sys.exit(1)
if not SRC.exists():
    print(f"找不到 AGH 生成的文件 {SRC}")
    sys.exit(1)

backend = EDABackend(timeout=60)
code = SRC.read_text(encoding="utf-8")
print(f"EDA 工具：{backend.discover()}")
print(f"复验对象：{SRC.name}（AGH 真实会话产出，{len(code)} 字符）")

rec = evaluate_once(spec, code, backend, HERE / "runs" / "_crosscheck", attempt=0)
data = rec.to_dict()
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

print("\n———— 复验结果 ————")
print(f"  裁决        ：{'PASS' if data['ok'] else 'FAIL'}")
for t in data.get("tools_called", []):
    print(f"  {t.get('tool'):<10} 返回码={t.get('returncode')}  ok={t.get('ok')}")
cmp_ = data.get("compare") or {}
print(f"  逐向量比对  ：{cmp_.get('matched', 0)}/{cmp_.get('total', 0)} 一致，"
      f"通过率 {cmp_.get('pass_rate', 0):.2%}")
if not data["ok"]:
    print(f"  失败类别    ：{data.get('failure_class')}")
    print(f"  裁判说明    ：{data.get('detail')}")
print(f"\n已写入 {OUT}")
