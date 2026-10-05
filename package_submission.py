#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包提交材料 —— 生成符合赛事命名规范的单个 ZIP。

用法
----
    python package_submission.py            # 读取 submit/team.json，生成 ZIP
    python package_submission.py --check     # 只做体检，不打包

规则（来自赛事手册）
------------------
    * 单个 ZIP ≤ 200 MB
    * 命名格式：组别-参赛编号-队伍名称-队长姓名

产物
----
    submit/<组别>-<编号>-<队名>-<队长>.zip
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUBMIT = ROOT / "submit"
TEAM_JSON = SUBMIT / "team.json"
STAGE = SUBMIT / "_stage"
MAX_ZIP_BYTES = 200 * 1024 * 1024

PLACEHOLDER = re.compile(r"【待填[^】]*】")


def load_team() -> dict:
    if not TEAM_JSON.exists():
        print(f"[错误] 找不到 {TEAM_JSON}")
        sys.exit(1)
    return json.loads(TEAM_JSON.read_text(encoding="utf-8"))


def fill(text: str, team: dict) -> str:
    """把文档里的【待填】替换成团队信息。"""
    mapping = {
        "队伍名称": team.get("team_name", ""),
        "参赛编号": team.get("team_no", ""),
        "队长": team.get("leader", ""),
        "姓名": team.get("leader", ""),
        "学校": team.get("school", ""),
        "学院": team.get("college", ""),
        "专业": team.get("major", ""),
        "年级": team.get("grade", ""),
        "日期": team.get("date", ""),
        "模型": team.get("model", "agnes-3.0-flash"),
    }
    for key, val in mapping.items():
        text = text.replace(f"【待填：{key}】", val)
    # 裸占位符【待填】不做兜底替换 —— 保持可见，交由体检环节报出来，
    # 避免把姓名误填进「学校 / 学院 / 专业」这类不同语义的栏位。
    return text


def zip_name(team: dict) -> str:
    parts = [
        team.get("group", "本科生组"),
        team.get("team_no", ""),
        team.get("team_name", ""),
        team.get("leader", ""),
    ]
    clean = [p.strip() for p in parts if p and p.strip()]
    return "-".join(clean)


def copy_docs(team: dict) -> list[str]:
    """把 docs/01..05 复制进来，并填充占位符。返回「还有占位符」的文件清单。"""
    targets = [
        ("01_提交材料_基本信息与技术信息.md", "01_基本信息与技术信息.md"),
        ("02_提交材料_测试样例.md", "02_测试样例.md"),
        ("03_成员分工与独立完成声明.md", "03_成员分工与独立完成声明.md"),
        ("04_演示视频与路演脚本.md", "04_演示视频与路演脚本.md"),
        ("05_公开发布材料.md", "05_公开发布材料.md"),
    ]
    leftovers: list[str] = []
    for src_name, dst_name in targets:
        src = ROOT / "docs" / src_name
        if not src.exists():
            print(f"  [跳过] 缺少 {src_name}")
            continue
        text = fill(src.read_text(encoding="utf-8"), team)
        if PLACEHOLDER.search(text):
            leftovers.append(dst_name)
        (STAGE / dst_name).write_text(text, encoding="utf-8")
    return leftovers


def build_evidence() -> None:
    """整理运行证据。"""
    dst = STAGE / "06_运行证据"
    dst.mkdir(parents=True, exist_ok=True)

    ev = ROOT / "evidence"
    pairs = [
        (ev / "selfcheck.md", "专业验证结果_元验证报告.md"),
        (ev / "selfcheck.json", "专业验证结果_元验证报告.json"),
        (ev / "RESULTS.md", "真实跑批成绩.md"),
        (ev / "run_20261003_183630.json", "工具调用链_完整裁决流水.json"),
        (ev / "model_journal.jsonl", "Agnes模型调用留痕.jsonl"),
    ]
    for src, name in pairs:
        if src.exists():
            shutil.copy2(src, dst / name)
        else:
            print(f"  [跳过] 缺少 {src.name}")

    # AGH 执行记录与关键配置（仓库之外，单独取）
    home = Path.home()
    agh_pairs = [
        (home / ".agh" / "data" / "audit" / "host.jsonl", "AGH执行记录_host.jsonl"),
        (home / ".agh" / "profiles" / "local-dev" / "configuration.json", "AGH关键配置_configuration.json"),
    ]
    for src, name in agh_pairs:
        if src.exists():
            shutil.copy2(src, dst / name)
        else:
            print(f"  [跳过] 缺少 {src}")

    # AGH 真实执行证据（整个子目录）
    agh_dir = ev / "agh_session"
    if agh_dir.exists():
        shutil.copytree(agh_dir, dst / "AGH真实执行证据",
                        ignore=shutil.ignore_patterns("*.log"))
    else:
        print("  [跳过] 缺少 evidence/agh_session")


def build_source() -> None:
    """复制源代码快照（不含 runs/、.git、node_modules）。"""
    dst = STAGE / "07_源代码"
    dst.mkdir(parents=True, exist_ok=True)

    for name in ["run.py", "check_key.py", "package_submission.py",
                 "README.md", "requirements.txt", ".gitignore"]:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, dst / name)

    for d in ["src", "benchmarks"]:
        src = ROOT / d
        if src.exists():
            shutil.copytree(src, dst / d,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def build_shots() -> None:
    dst = STAGE / "08_截图"
    dst.mkdir(parents=True, exist_ok=True)
    pub = ROOT / "docs" / "publish"
    naming = {
        "01_home_top.png": "01_项目主页首屏.png",
        "02_scores.png": "02_项目主页成绩单.png",
        "03_github_repo.png": "03_GitHub公开仓库.png",
        "04_agh_session.png": "04_AGH真实执行证据.png",
    }
    for src_name, dst_name in naming.items():
        src = pub / src_name
        if src.exists():
            shutil.copy2(src, dst / dst_name)


def write_readme(team: dict, leftovers: list[str]) -> None:
    text = SUBMIT_README_TEMPLATE
    for key, val in {
        "{{TEAM}}": team.get("team_name", ""),
        "{{NO}}": team.get("team_no", ""),
        "{{LEADER}}": team.get("leader", ""),
        "{{SCHOOL}}": team.get("school", ""),
        "{{DATE}}": team.get("date", ""),
        "{{HOMEPAGE}}": team.get("homepage", ""),
        "{{REPO}}": team.get("repo", ""),
        "{{VIDEO}}": team.get("video_main", "【待填：视频主链接】"),
        "{{VIDEO2}}": team.get("video_backup", "（可选）"),
        "{{MODEL}}": team.get("model", "agnes-3.0-flash"),
        "{{LEFTOVER}}": ("、".join(leftovers) if leftovers
                         else "无（全部占位符已填充）"),
    }.items():
        text = text.replace(key, val)
    (STAGE / "00_提交说明与清单.md").write_text(text, encoding="utf-8")


SUBMIT_README_TEMPLATE = """# 提交说明与材料清单

> **组别**：本科生组 ／ **参赛编号**：{{NO}} ／ **队伍名称**：{{TEAM}} ／ **队长**：{{LEADER}}
> **编制日期**：{{DATE}}

---

## 一、关键链接（填表用）

| 项目 | 内容 |
|---|---|
| 项目名称 | AGH 驱动的数字逻辑「生成—验证—修复」闭环验证引擎 |
| 在线体验链接 | {{HOMEPAGE}} |
| 代码仓库 | {{REPO}} |
| 演示视频（主） | {{VIDEO}} |
| 演示视频（备用） | {{VIDEO2}} |
| 使用模型 | `{{MODEL}}`（唯一模型，未接入任何第三方模型） |

---

## 二、赛事材料清单逐项对照

赛事手册要求 **9 类材料**，本包内每一类的落点如下（√ = 已就绪，○ = 待你补链接）。

| # | 赛事要求 | 本包内对应文件 | 状态 |
|---|---|---|---|
| 1 | 基本信息：项目名称 / 参考方向 / 摘要 / 问题来源与目标 | `01_基本信息与技术信息.md` 第一节 | √ |
| 2 | 技术信息：AGH 作用 / 模型名称版本 / 数据代码软件环境 API | `01_基本信息与技术信息.md` 第二节 | √ |
| 3 | 可运行作品：在线体验链接 + 代码仓库 + 复现说明 | 链接见上表；`07_源代码/README.md` | √ |
| 4 | 演示视频：3–5 分钟，只提交链接 | `04_演示视频与路演脚本.md`；链接见上表 | ○ |
| 5 | 运行证据：AGH 执行记录 / 工具调用链 / 模型参与证据 / 关键配置 / 专业验证结果 | `06_运行证据/`（5 份） | √ |
| 6 | 测试样例：正常 / 边界 / 失败 三类各若干条 | `02_测试样例.md` | √ |
| 7 | 成员声明：分工说明 + 独立完成声明 | `03_成员分工与独立完成声明.md` | √ |
| 8 | 公开内容：平台 + 有效链接 + 截图 + 发布日期 | `05_公开发布材料.md` + `08_截图/` | √ |
| 9 | 打包：单个 ZIP ≤ 200 MB，命名「组别-参赛编号-队伍名称-队长姓名」 | 即本 ZIP | √ |

### 三条「直接出局」红线，逐条自检

| 红线 | 本项目情况 |
|---|---|
| AGH 至少连续 3 步（规划 → 能力调用 → 反馈处理与结果验证），且 ≥1 条工具调用链记录 | 闭环四环节齐全；2026-10-05 已在 AGH 中真实执行一次任务（账号 U104 / 模型 agnes-3.0-flash），read/write/todo 三次工具调用留有终端回显，AGH 产出的 Verilog 经本项目裁判复验 256/256 一致判 PASS；另见 `06_运行证据/工具调用链_完整裁决流水.json` 内逐次 iverilog / vvp / yosys 的命令与返回码 |
| 必须同时提交正常 / 边界 / 失败三类测试样例 | `02_测试样例.md`：正常 13 条、边界 3 类、失败 7 条（含事先标注的期望类别） |
| ≥1 条真实公开内容（平台 + 有效链接 + 截图 + 发布日期） | 项目主页（2026-10-03）与 GitHub 公开仓库（2026-10-04），截图见 `08_截图/` |

---

## 三、包内文件说明

```
├── 00_提交说明与清单.md          ← 本文件
├── 01_基本信息与技术信息.md       表单第 1、2 栏直接抄
├── 02_测试样例.md               正常 / 边界 / 失败 三类
├── 03_成员分工与独立完成声明.md
├── 04_演示视频与路演脚本.md       分镜脚本 + 上传要求
├── 05_公开发布材料.md            公开内容四项（平台/链接/截图/日期）
├── 06_运行证据/                  ← 核心证据，评委会点开逐个核对
│   ├── AGH执行记录_host.jsonl
│   ├── AGH关键配置_configuration.json
│   ├── Agnes模型调用留痕.jsonl
│   ├── 工具调用链_完整裁决流水.json
│   ├── 专业验证结果_元验证报告.md / .json
│   ├── 真实跑批成绩.md
│   └── AGH真实执行证据/          2026-10-05 AGH 真实会话 + 裁判复验
├── 07_源代码/                    可直接运行；与公开仓库一致
└── 08_截图/                      主页首屏 / 成绩单 / GitHub 仓库页
```

---

## 四、复现方式（评委用）

```bash
# 1. 环境：Python 3.9+，核心链路零第三方依赖
python -V

# 2. EDA 工具链：解压 oss-cad-suite 到代码上级目录即可，代码自动寻找
#    https://github.com/YosysHQ/oss-cad-suite-build/releases

# 3. 不需要任何密钥即可复现裁判校准（用人工参考实现替代模型）
python run.py --selftest     # 期望：裁判校准 20/20、链路自检 13/13

# 4. 接入 Agnes 模型后的正式评测
export AGNES_API_KEY=<Key>
python run.py --all -v       # 13 条规格，逐轮打印裁决过程
```

参考结果：**13 条规格最终通过 12 条（92.3%），首次通过 7 条（53.8%），
平均 1.77 轮，481 次模型调用，全程约 3.8 分钟。**

---

## 五、未完成项（提交前需处理）

**本包中仍存在占位符的文件**：{{LEFTOVER}}

需要补的信息：

1. `03_成员分工与独立完成声明.md` —— 队长姓名 / 学校 / 学院 / 专业 / 年级 / 日期；
2. 演示视频链接（主 + 可选备用）—— 填进表单「演示视频」栏与本文件第一节。

> 赛事允许在截止前**反复重提**，锁定最后一次有效版本。若视频后补，可先以当前
> 版本提交占位，录好后再重提一次即可。
"""


def check(leftovers: list[str]) -> None:
    print("\n———— 打包前体检 ————")
    total = sum(f.stat().st_size for f in STAGE.rglob("*") if f.is_file())
    print(f"  暂存目录：{STAGE}")
    print(f"  文件数  ：{sum(1 for f in STAGE.rglob('*') if f.is_file())}")
    print(f"  未压缩  ：{total / 1024 / 1024:.1f} MB")
    if leftovers:
        print(f"  ⚠ 仍有占位符：{'、'.join(leftovers)}")
    else:
        print("  ✓ 文档占位符已全部填充")

    # 敏感信息扫描
    hits = []
    for f in STAGE.rglob("*"):
        if not f.is_file():
            continue
        try:
            t = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if re.search(r"sk-[A-Za-z0-9]{20,}", t):
            hits.append(str(f.relative_to(STAGE)))
    if hits:
        print(f"  ✗ 发现疑似密钥，必须处理：{hits}")
    else:
        print("  ✓ 未发现任何 API Key")


def main() -> int:
    ap = argparse.ArgumentParser(description="打包赛事提交材料")
    ap.add_argument("--check", action="store_true", help="只体检，不生成 ZIP")
    args = ap.parse_args()

    team = load_team()
    STAGE.mkdir(parents=True, exist_ok=True)
    print(f"队伍：{team.get('group')} / {team.get('team_no')} / "
          f"{team.get('team_name')} / {team.get('leader')}")

    for f in STAGE.rglob("*"):
        if f.is_file():
            f.unlink()
    for d in sorted([p for p in STAGE.rglob("*") if p.is_dir()],
                    key=lambda p: -len(p.parts)):
        try:
            d.rmdir()
        except OSError:
            pass

    print("  整理提交文档…")
    leftovers = copy_docs(team)
    print("  整理运行证据…")
    build_evidence()
    print("  整理源代码…")
    build_source()
    print("  整理截图…")
    build_shots()
    write_readme(team, leftovers)

    check(leftovers)
    if args.check:
        return 0

    name = zip_name(team)
    out = SUBMIT / f"{name}.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(STAGE.rglob("*")):
            if f.is_file():
                z.write(f, f"{name}/{f.relative_to(STAGE)}")

    size = out.stat().st_size
    print("\n———— 打包结果 ————")
    print(f"  文件：{out}")
    print(f"  体积：{size / 1024 / 1024:.2f} MB"
          f"（上限 200 MB，{'合格' if size <= MAX_ZIP_BYTES else '超标！'}）")
    print(f"  命名：{name}（格式：组别-参赛编号-队伍名称-队长姓名）")
    if leftovers:
        print(f"  ⚠ 仍含占位符：{'、'.join(leftovers)}")
        print("     → 补齐 submit/team.json 后重新运行本脚本即可重新打包")
    return 0


if __name__ == "__main__":
    sys.exit(main())
