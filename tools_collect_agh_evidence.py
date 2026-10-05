# -*- coding: utf-8 -*-
"""归档 AGH 真实会话证据：会话清单、会话详情、HTML 导出、执行日志。

产物落在 evidence/agh_session/ 下，供提交包「运行证据」使用。
用法： python tools_collect_agh_evidence.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

PROJ = Path(__file__).resolve().parent
HARNESS = Path("C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/tools/agnes-harness")
NODE24 = "C:/Users/liumi/WorkBuddy/2026-10-02-20-04-02/tools/node24/node.exe"
AGH = HARNESS / "packages/cli/dist/local/agnes.mjs"
OUT = PROJ / "evidence" / "agh_session"
OUT.mkdir(parents=True, exist_ok=True)

# 本机 AGH 的审计日志与关键配置（在仓库之外，需要单独取）
HOME = Path.home()
EXTRA = [
    (HOME / ".agh" / "data" / "audit" / "host.jsonl", "AGH执行记录_host.jsonl"),
    (HOME / ".agh" / "profiles" / "local-dev" / "configuration.json",
     "AGH关键配置_configuration.json"),
]


def agh(args: list[str], tag: str) -> str:
    p = subprocess.run([NODE24, str(AGH), *args], cwd=str(HARNESS),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore", timeout=180)
    text = (p.stdout or "") + ("\n[stderr]\n" + p.stderr if p.stderr else "")
    (OUT / f"{tag}.txt").write_text(text, encoding="utf-8")
    return text


print("== 1) 会话清单 ==")
listing = agh(["sessions", "list"], "01_会话清单")
print(listing[:800])

# 会话 ID 必须用完整键（agnes:local:<profile>:cli:session:<uuid>），只给 uuid 会报 no session
ids = re.findall(r"agnes:local:[^:\s]*:cli:session:[0-9a-f-]{36}", listing)
ids = list(dict.fromkeys(ids))
if not ids:
    short = re.findall(r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
                       listing)
    ids = ["agnes:local:local-dev:cli:session:" + s for s in dict.fromkeys(short)]
print(f"发现 {len(ids)} 个会话：{ids}")

for i, sid in enumerate(ids[:6], start=1):
    short = sid.rsplit(":", 1)[-1][:8]        # 完整键里取出 uuid 前 8 位做文件名
    print(f"== 2.{i}) 会话 {short} 详情 ==")
    agh(["sessions", "show", sid], f"02_{i}_会话详情_{short}")
    print(f"== 3.{i}) 导出 HTML ==")
    html_out = OUT / f"03_{i}_会话导出_{short}.html"
    p = subprocess.run(
        [NODE24, str(AGH), "export", sid, "--html", "-o", str(html_out.resolve())],
        cwd=str(HARNESS), capture_output=True, text=True,
        encoding="utf-8", errors="ignore", timeout=240)
    print("  export:", (p.stdout or p.stderr or "")[:160])
    if not html_out.exists():
        print(f"  [跳过] 未生成 {html_out.name}")

print("== 4) 拷贝审计日志与配置 ==")
for src, name in EXTRA:
    if src.exists():
        shutil.copy2(src, OUT / name)
        print(f"  ✓ {name}")
    else:
        print(f"  [跳过] {src}")

print("== 5) 拷贝执行日志并生成可读实录 ==")
runs = PROJ / "runs"
for pat in ["_pty_tui_print.log", "_pty_print3_stdout.txt", "_pty_print4_stdout.txt",
            "_pty_mcpadd.log", "_pty_fix_stdout.txt", "_pty_http_stdout.txt",
            "_pty_tui_yolo.log"]:
    src = runs / pat
    if src.exists():
        shutil.copy2(src, OUT / pat.replace("_pty_", "AGH"))
        print(f"  ✓ {pat}")

import re  # noqa: E402
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
src = runs / "_pty_tui_print.log"
if src.exists():
    raw = src.read_text(encoding="utf-8", errors="ignore")
    lines = [ln.rstrip() for ln in _ANSI.sub("", raw).splitlines()]
    keep = [ln for ln in lines if ln.strip().startswith("- ")]
    (OUT / "04_AGH会话实录_工具调用链.md").write_text(
        "# AGH 真实会话实录（工具调用链）\n\n"
        "来源：AGH 一次性任务模式在本项目工作区实际执行时的终端回显，"
        "每一行 `tool · ok · <耗时>` 即一次真实工具调用。\n\n"
        "```\n" + "\n".join(keep) + "\n```\n",
        encoding="utf-8")
    print("  ✓ 04_AGH会话实录_工具调用链.md")

summary = {
    "note": "AGH 真实会话证据。01/02/03 为会话清单、详情与 HTML 导出；"
            "AGH执行记录_host.jsonl 为 AGH 主机审计日志；"
            "AGH关键配置_configuration.json 为账号与模型配置（U104 / agnes-3.0-flash）。",
    "sessionIds": ids,
}
(OUT / "README.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
print(f"\n完成，产物在 {OUT}")
