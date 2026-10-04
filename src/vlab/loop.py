"""闭环控制器：规划 → 实现 → 验证 → 归因 → 修复，循环直到通过或耗尽预算。

这里是 AGH 真正编排的那段逻辑。它刻意做成了「可脱离 AGH 独立运行」的形态：
本地可以直接 import 跑通，接入 AGH 时把各阶段注册成 MCP 工具即可，
业务决策逻辑一行都不用改。

与普通「把报错丢回给模型重试」的做法相比，差别在两点：

1. **失败先分类，再按类给药方**
   每一类失败有专门的修复提示构造方式：语法错误喂编译器原文、
   接口错误喂逐项差异、迟到/早到喂具体偏移拍数、功能错误喂反例向量表。
   盲目重试只是在碰运气，分类之后修复才是有信息的。

2. **历史进入上下文**
   每一轮修复都会带上此前失败过的类别与代码，避免模型原地打转
   反复掉进同一个坑。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .eda import EDABackend
from .harness import evaluate_once, EvalRecord
from .specs import Spec, golden_path
from .agnes import AgnesClient, extract_verilog, ModelCallError


SYSTEM_PROMPT = """你是一名严谨的数字电路设计工程师，使用 Verilog-2001 可综合子集。
只输出要求的内容，不要写解释性散文。所有寄存器必须有明确的复位。"""


def _ports_text(spec: Spec) -> str:
    """把规格里的端口表渲染成 Verilog 声明的样子，供提示词引用。

    spec.ports 直接来自 JSON，元素为 dict 而非 Port 对象，这里统一按 dict 取值。
    """
    lines = []
    for p in spec.ports:
        direction = p["direction"]
        width = int(p.get("width", 1))
        rng = f"[{width - 1}:0] " if width > 1 else ""
        lines.append(f"    {direction:6s}{rng}{p['name']}")
    return "\n".join(lines)


# 从真实跑批中归纳出的高频错误（2026-10-03 首轮 13 题实测：4 道失败中 3 道卡在
# 重复声明端口 与 case 当表达式用）。写成显式负例，比抽象的"注意语法"有效得多。
COMMON_PITFALLS = """【三个最常见的编译错误，务必避开】
1. 端口重复声明：写了 `output [1:0] y;` 之后，**不要再写** `reg [1:0] y;`。
   需要寄存器输出时，直接写成 `output reg [1:0] y;`。
2. `case` 不是表达式：**禁止** `assign y = case(sel) ...;`。
   正确写法：
   always @(*) begin
     case (sel)
       2'b00: y = a;
       default: y = b;
     endcase
   end
3. 只允许 Verilog-2001 语法：禁止 `logic` / `always_ff` / `always_comb` /
   `enum` / `struct` / `unique case` 等 SystemVerilog 写法，一律用
   `reg` / `wire` 与 `always @(posedge clk or negedge rst_n)`。
"""


def build_plan_prompt(spec: Spec) -> str:
    ports = _ports_text(spec)
    return f"""你要设计下面这个数字逻辑模块。请先给出设计规划，**不要输出完整代码**。

【任务】{spec.title}
【功能规格】{spec.description}

【必须严格遵守的接口契约】
module {spec.module} 的端口必须如下（顺序无关）：

{ports}

【输出格式】只输出一个 JSON 对象，不要代码块，不要额外文字：
{{
  "kind": "combinational" 或 "sequential",
  "approach": "一句话说明实现思路，不超过 40 字",
  "state": "若含时序逻辑，描述需要哪些寄存器及其复位行为；纯组合逻辑填 null",
  "risks": ["最容易写错的 1~3 个点"]
}}
"""


def build_implement_prompt(spec: Spec, plan: dict) -> str:
    ports = _ports_text(spec)
    hint = ""
    if spec.is_sequential:
        hint = ("\n【时序要求】输出必须是**寄存器输出**（Moore 型）："
                "状态与输出都在时钟边沿统一更新，不要把输出写成 assign 组合表达式，"
                "否则会比参考实现早出现一个时钟周期。\n")
    return f"""请按下面的规划实现 Verilog 模块。

【任务】{spec.title}
【功能规格】{spec.description}

【已确定的设计规划】
{json.dumps(plan, ensure_ascii=False, indent=2)}
{hint}
【硬性约束】
1. module 名必须是 `{spec.module}`；
2. 端口必须如下，名称、方向、位宽完全一致：

{ports}

3. **禁止**使用 parameter / localparam / `#(...)`；
4. 只写这一个 module，不要写 testbench，不要 $display；
5. 组合逻辑的所有分支必须完整赋值，不得推断出锁存器；
6. 时序逻辑必须异步低电平复位 rst_n。

{COMMON_PITFALLS}
【输出】只输出 Verilog 源码，用 ```verilog 代码块包裹。
"""


def build_repair_prompt(spec: Spec, previous: str, history: list[dict]) -> str:
    last = history[-1]
    cls = last["class"]
    playbook = {
        "SYNTAX": (
            "编译器报错。请逐条对照下面的报错行号修正。三个最高频原因：\n"
            "  (a) 端口重复声明——报错含 'already been declared' 时，删掉多余的 "
            "`reg`/`wire` 声明，改成 `output reg [w-1:0] 名字;` 一次性写完；\n"
            "  (b) 把 case 当表达式用——报错含 'Syntax error in continuous assignment' "
            "时，把 assign 改成 `always @(*) begin case(...) ... endcase end`；\n"
            "  (c) 用了 SystemVerilog 关键字（logic / always_ff / always_comb / enum），"
            "改回 Verilog-2001 写法。"
        ),
        "INTERFACE": (
            "端口不符合规格。请**逐字比照**规格里的端口表重写端口列表，"
            "特别注意每个信号的位宽——这是最常见的不一致点。"
        ),
        "LATCH": (
            "综合后发现推断出了锁存器，说明组合逻辑分支不完整。"
            "请为 if / case 的每个分支都覆盖到全部输出，补 default 或在开头先赋默认值。"
        ),
        "TIMEOUT": (
            "仿真超时，很可能存在组合反馈环（例如把某个信号的输出又接回它自己的输入）。"
            "请检查是否存在无寄存器的自反馈路径。"
        ),
        "RESET": (
            "复位释放后输出处于不定态 X。请确认每个寄存器都在复位分支中被赋初值，"
            "敏感列表写法为 always @(posedge clk or negedge rst_n)。"
        ),
        "TIMING_SHIFT": (
            "逻辑本身是对的，但输出节拍不对。"
            "若判定为**超前**：说明你把输出写成了 assign 组合表达式，"
            "请改为寄存器输出（在 always 块中用 <= 赋值）；"
            "若判定为**滞后**：说明你多打了一级寄存器，请去掉多余的那一级。"
        ),
        "VALUE_MISMATCH": (
            "存在使输出与参考不一致的输入向量。请重点检查：边界条件（全 0、全 1、"
            "相等、溢出）、运算符的符号性与位宽截断、优先级。"
        ),
    }
    advice = playbook.get(cls, "请根据下面的证据重新检查实现。")
    tried = "\n".join(f"  第{i+1}次尝试：{h['class']}" for i, h in enumerate(history))

    return f"""你上一版实现没有通过等价性验证，请修复。

【任务】{spec.title}
【功能规格】{spec.description}

【本次失败类别】{cls}
【修复方向】{advice}

【验证器给出的证据】
{chr(10).join('  - ' + e for e in last['evidence']) or '  （无）'}

【已失败的尝试】（避免重复踩同一个坑）
{tried}

【你上一版的代码】
```verilog
{previous}
```

【硬性约束】module 名必须是 `{spec.module}`；端口名称/方向/位宽必须与规格完全一致；
禁止 parameter；不要写 testbench。

{COMMON_PITFALLS}
【输出】只输出修正后的完整 Verilog 源码，用 ```verilog 代码块包裹。
"""


@dataclass
class TaskResult:
    spec_id: str
    ok: bool
    attempts: int = 0
    first_try_ok: bool = False
    failure_class: str | None = None
    final_detail: str = ""
    records: list[dict] = field(default_factory=list)
    model_calls: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    final_source: str = ""

    def to_dict(self) -> dict:
        return {
            "spec_id": self.spec_id, "ok": self.ok, "attempts": self.attempts,
            "first_try_ok": self.first_try_ok, "failure_class": self.failure_class,
            "final_detail": self.final_detail, "seconds": round(self.seconds, 2),
            "records": self.records, "model_calls": self.model_calls,
        }


# --------------------------------------------------------------------- 主流程
def run_single_task(spec: Spec, model, backend: EDABackend, workdir: Path,
                    max_attempts: int = 4, on_attempt=None) -> TaskResult:
    """在一个规格上跑完整的闭环。

    on_attempt：可选的回调 `f(attempt_index, record_dict)`，每轮裁决结束后调用，
    用于把过程实时打到终端（演示录像用，不影响判定逻辑）。
    """
    import time
    t0 = time.time()
    res = TaskResult(spec_id=spec.id, ok=False)
    history: list[dict] = []
    source = ""

    for attempt in range(max_attempts):
        res.attempts = attempt + 1
        # ---- 步骤 1：规划
        if attempt == 0:
            plan_raw = model.chat(build_plan_prompt(spec), system=SYSTEM_PROMPT,
                                  purpose="plan", temperature=0.1)
            plan = _safe_json(plan_raw)
        else:
            plan = {"approach": "按修复提示修订", "kind": spec.kind}

        # ---- 步骤 2：实现（首轮生成 / 后续修复）
        if attempt == 0:
            prompt = build_implement_prompt(spec, plan)
            purpose = "implement"
        else:
            prompt = build_repair_prompt(spec, source, history)
            purpose = "repair"

        raw = model.chat(prompt, system=SYSTEM_PROMPT, purpose=purpose, temperature=0.2)
        candidate = extract_verilog(raw)
        if not candidate.strip():
            history.append({"class": "EMPTY_OUTPUT", "detail": "模型未返回代码", "evidence": []})
            continue
        if f"module {spec.module}" not in candidate:
            # 轻微的自我保护：确保至少 module 名正确，让后续能落到真实分类上
            candidate = re.sub(r"\bmodule\s+([A-Za-z_]\w*)", f"module {spec.module}", candidate, count=1)
        source = candidate

        # ---- 步骤 3：工具层验证
        rec = evaluate_once(spec, candidate, backend, workdir, attempt=attempt)
        res.records.append(rec.to_dict())

        if on_attempt is not None:
            on_attempt(attempt, rec.to_dict())

        if rec.ok:
            res.ok = True
            res.first_try_ok = (attempt == 0)
            res.final_source = candidate
            break

        history.append({
            "class": rec.failure_class or "UNKNOWN",
            "detail": rec.detail,
            "evidence": rec.evidence[:4],
        })
        res.failure_class = rec.failure_class

    if not res.ok and history:
        res.final_detail = history[-1]["detail"]
    if hasattr(model, "journal"):
        res.model_calls = model.journal
    res.seconds = time.time() - t0
    return res


def _safe_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


# --------------------------------------------------------------------- 自校准模型
class GoldenReferenceModel:
    """自校准替身：直接用人工参考实现充当「模型输出」。

    用途只有一个 —— 在还没有 Agnes API Key 时验证整条链路是否通畅。
    它**不是模型**，也不会被用来产生任何评测统计数据。
    """
    def __init__(self) -> None:
        self.journal: list[dict] = []

    def chat(self, prompt: str, system: str = "", purpose: str = "selfcheck",
             temperature: float = 0.0, max_tokens: int = 0) -> str:
        self.journal.append({"purpose": purpose, "model": "golden-reference(selfcheck)",
                             "ok": True, "seconds": 0.0})
        if purpose == "plan":
            return '{"kind": "see-spec", "approach": "参考实现", "state": null, "risks": []}'
        return f"```verilog\n{_lookup_reference(prompt)}\n```"


def _lookup_reference(prompt: str) -> str:
    """按提示词中出现的 module 名，找出对应的参考实现并返回改名后的源码。"""
    table = {spec.module: _rename_reference(spec) for spec in _iter_specs()}
    cands = re.findall(r"[A-Za-z_]\w*", prompt)
    hits = [c for c in cands if c in table]
    if not hits:
        return ""
    # 规格里 module 名可能出现多次，取出现次数最多的那个更稳
    best = max(set(hits), key=hits.count)
    return table[best]


def _rename_reference(spec) -> str:
    src = golden_path(spec).read_text(encoding="utf-8")
    return re.sub(rf"\b{spec.golden_module}\b", spec.module, src)


def _iter_specs():
    from .specs import load_specs
    return load_specs()
