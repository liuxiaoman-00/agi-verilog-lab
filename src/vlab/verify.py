"""等价性验证引擎：测试台自动生成 → 穷举激励 → 双路比对 → 失败分类。

这是本项目「可验证性」的核心。关键设计：

1. **测试台自动生成，不靠人工写用例**
   激励由规格声明的输入空间自动构造（穷举或「边界集 + 固定种子随机」），
   因此「验证是否充分」这件事本身可以被度量（见 mutation.py 的变异得分）。

2. **双路比对（dual-rail）**
   测试台同时例化 DUT（AI 生成）与 golden（人工参考实现），施加完全相同的激励，
   逐周期dump出两条输出轨迹，由 Python 侧做比对。

3. **延迟错位检测（timing-shift detection）**
   这是本项目最有工程味道的一处：很多 FSM 实现**逻辑是对的，只是输出晚了一拍**。
   如果只是简单比对，它会被判成「功能错误」，修复建议也就跟着跑偏。
   这里会做 lag=0..MAXLAG 的移位重比对，把它单独识别成 TIMING_SHIFT 类，
   从而给出完全不同的修复策略。

4. **失败分类学**
   所有失败被归到有限几类，每类对应一条修复策略——这才构成「闭环」，
   而不是把报错原文丢回模型碰运气。
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from .iface import ModuleInfo, InterfaceDiff


# --------------------------------------------------------------------- 激励生成
def boundary_vectors(width: int, max_extra: int = 4096) -> list[int]:
    """有工程意义的边界向量：全0、全1、走1、走0、相邻位翻转。"""
    if width <= 0:
        return []
    vs: list[int] = []
    full = (1 << width) - 1
    vs += [0, full]
    for i in range(width):
        vs.append(1 << i)                 # walking 1
        vs.append(full ^ (1 << i))        # walking 0
    for i in range(width - 1):            # 相邻位
        vs.append((1 << i) | (1 << (i + 1)))
        vs.append(full ^ ((1 << i) | (1 << (i + 1))))
    seen, out = set(), []
    for v in vs:
        if v not in seen and v <= full:
            seen.add(v)
            out.append(v)
    return out[:max_extra]


def de_bruijn(k: int, n: int) -> list[int]:
    """生成 de Bruijn 序列 B(k, n)。

    用它作为串行激励的理由：任意长度为 n 的输入序列都会在序列中出现恰好一次。
    对于顺序敏感的时序电路（移位寄存器、序列检测器、FSM），这比随机激励强得多——
    它是「在 n 阶窗口意义上完备」的，覆盖率可以被严格保证而非估计。
    """
    a = [0] * (k * n)
    seq: list[int] = []

    def db(t: int, p: int) -> None:
        if t > n:
            if n % p == 0:
                seq.extend(a[1:p + 1])
        else:
            a[t] = a[t - p]
            db(t + 1, p)
            for j in range(a[t - p] + 1, k):
                a[t] = j
                db(t + 1, t)          # 注意是 t 而不是 1：Lyndon 字嵌套要求复位到 t

    db(1, 1)
    return seq + seq[:n - 1] if n > 1 else seq


def generate_stimulus(width: int, mode: str, n: int = 512, seed: int = 20260701,
                      exhaustive_limit: int = 1 << 14, spec_order: int = 6) -> dict:
    """构造激励向量表。返回 {"vectors": [...], "mode": 实际模式, "coverage": float}。"""
    if width <= 0:
        return {"vectors": [], "mode": "empty", "coverage": 1.0, "space": 1}

    space = 1 << width

    if mode == "constant":
        return {"vectors": [0] * n, "mode": "constant", "coverage": 1.0, "space": space}

    if mode == "debruijn":
        order = int(spec_order)
        seq = de_bruijn(2, order) if width == 1 else None
        if seq:
            # 补上边界分布：全 0 / 全 1 / 交替，接在 de Bruijn 序列之前
            prefix = [0, 1] + ([0] * (order + 1)) + ([1] * (order + 1)) + [1, 0, 1, 0, 1, 1, 0, 0]
            vectors = prefix + seq
            return {"vectors": vectors, "mode": f"debruijn(k={order})",
                    "coverage": 1.0, "space": space}

    if mode == "exhaustive" and space <= exhaustive_limit and n <= exhaustive_limit:
        vectors = list(range(space))
        return {"vectors": vectors, "mode": "exhaustive", "coverage": 1.0, "space": space}

    rng = random.Random(seed)
    vs = boundary_vectors(width)
    seen = set(vs)

    # 输入空间可能比需求条数小（例如 cnt12 只有 64 种取值却要求 600 条）。
    # 这里必须同时用「条数」和「空间耗尽」两个条件兜住，否则一旦空间取尽，
    # 去重后的抽样会变成永远抽不到新值的死循环。
    for _ in range(n * 4):
        if len(vs) >= n or len(seen) >= space:
            break
        v = rng.getrandbits(width)
        if v not in seen:
            seen.add(v)
            vs.append(v)

    return {
        "vectors": vs,
        "mode": "boundary+random",
        "coverage": round(len(seen) / space, 6) if space <= exhaustive_limit
                    else round(len(seen) / n, 6),
        "space": space,
        "unique": len(seen),
    }


# --------------------------------------------------------------------- 测试台
TB_HEADER = """`timescale 1ns/1ps
module tb_vlab;
  localparam NSTIM = {nstim};
  localparam INW   = {inw};

  reg  [INW-1:0] stim [0:NSTIM-1];
  reg  [INW-1:0] in_vec;
  integer idx;

{clock_decl}{input_decls}{output_decls}
  {dut_mod} u_dut ({conn});
  {ref_mod} u_ref ({conn2});

  initial $readmemb("stim.txt", stim);

  initial begin
    in_vec = {{INW{{1'b0}}}};
{prime}{reset_seq}{loop_body}    $display("VLAB DONE");
    $finish;
  end

  initial begin
    #{watchdog};
    $display("VLAB TIMEOUT");
    $finish;
  end
endmodule
"""


def _bus_expr(names: list[str]) -> str:
    return "{" + ", ".join(names) + "}" if len(names) > 1 else names[0]


def render_testbench(spec: dict, dut_module: str, ref_module: str, stimuli: list[int],
                     in_width: int) -> str:
    """按规格渲染等价性测试台。"""
    is_seq = spec.get("kind", "combinational") == "sequential"
    clk = spec.get("clock", "clk")
    rst = spec.get("reset")
    active_low = spec.get("reset_active", "low") == "low"
    pol = "1'b0" if active_low else "1'b1"
    idle = "1'b1" if active_low else "1'b0"

    data_inputs = [p for p in spec["ports"]
                   if p["direction"] == "input" and p["name"] != clk and p["name"] != rst]
    outputs = [p for p in spec["ports"] if p["direction"] == "output"]

    # 所有 reg 必须显式赋初值：默认的 X 会让 `reg rst_n;` 在 t=0 出现 "X->0"
    # 的假 negedge，导致异步复位实际不生效，后续采样一路拖着 X 传播。
    clock_decl = ""
    if is_seq:
        clock_decl = f"  reg {clk} = 1'b0;\n  initial forever #5 {clk} = ~{clk};\n"

    input_decls = ""
    if is_seq:
        # 复位线初值直接取**有效电平**，让被测模块在第一个时钟沿就被可靠复位。
        # 依赖「t=2 时拉低产生 negedge」去异步复位并不可靠：某些仿真器
        # 对同一时刻的初始化与后续赋值的事件调度不同，复位会被悄悄吞掉，
        # 表现为输出拖着一段 X 慢慢被移位掉，很难定位。
        input_decls += f"  reg {rst} = {pol};\n"
    for p in data_inputs:
        w = int(p.get("width", 1))
        rng = f"[{w-1}:0] " if w > 1 else ""
        # 数据输入**刻意不赋初值**。
        # 若写成 reg [7:0] din = 8'h0，首个激励向量恰好也是 0 时就不会产生
        # 值变化事件，被测模块的 always @(*) 在 t=0 不被触发，
        # 输出会一直停在 X —— 这是非常隐蔽的一类「自校准都过不去」的假失败。
        # 保持默认 X，让 t=0 的第一次赋值形成 X->0 跳变，组合逻辑便会被正常触发。
        input_decls += f"  reg {rng}{p['name']};\n"

    # 从 in_vec 按位切分给各输入（MSB 优先对应 ports 顺序）
    slice_src = ""
    off = 0
    for p in data_inputs:
        w = int(p.get("width", 1))
        expr = f"in_vec[{in_width-1-off}]" if w == 1 else f"in_vec[{in_width-1-off} -: {w}]"
        off += w
        slice_src += f"      {p['name']} = {expr};\n"

    output_decls_decls = ""
    for p in outputs:
        w = int(p.get("width", 1))
        rng = f"[{w-1}:0] " if w > 1 else ""
        output_decls_decls += f"  wire {rng}{p['name']};\n  wire {rng}{p['name']}_ref;\n"

    dut_bus = _bus_expr([p["name"] for p in outputs])
    ref_bus = _bus_expr([f"{p['name']}_ref" for p in outputs])
    output_decls_decls += f"  wire [{max(1, sum(int(p.get('width',1)) for p in outputs))-1}:0] dut_bus = {dut_bus};\n"
    output_decls_decls += f"  wire [{max(1, sum(int(p.get('width',1)) for p in outputs))-1}:0] ref_bus = {ref_bus};\n"

    # 连线：除时钟/复位外同端口名直连，ref 侧用同名 _ref 信号
    conn_parts, conn2_parts = [], []
    for p in spec["ports"]:
        n, d = p["name"], p["direction"]
        if n == clk:
            conn_parts.append(f".{n}({clk})")
            conn2_parts.append(f".{n}({clk})")
        elif n == rst:
            conn_parts.append(f".{n}({rst})")
            conn2_parts.append(f".{n}({rst})")
        elif d == "input":
            conn_parts.append(f".{n}({n})")
            conn2_parts.append(f".{n}({n})")
        else:
            conn_parts.append(f".{n}({n})")
            conn2_parts.append(f".{n}({n}_ref)")

    # 复位：断言若干拍后释放，确保寄存器脱离 X 态
    reset_seq = ""
    if is_seq and rst:
        # 复位线初值直接取**有效电平**
        pol = "1'b0" if active_low else "1'b1"
        idle = "1'b1" if active_low else "1'b0"
        # 先在时钟沿完成复位，再沿后 #1 释放（避开与时钟沿同刻的竞态），
        # 额外让出一拍，使主循环严格对齐 10ns 节拍。
        reset_seq = (
            f"    repeat (3) @(posedge {clk});\n"
            f"    #1; {rst} = {idle};\n"
            f"    @(posedge {clk});\n"
        )

    # ── 每拍的时间安排（这是本项目最容易出错、也最关键的一处）────────────
    # 1) 输入必须在**时钟沿之后 #1** 再驱动。
    #    若与沿同时刻驱动，激励赋值与寄存器采样同处一个 delta 区，
    #    顺序不确定会让寄存器采到「本该下一拍才采到」的新值，
    #    表现为被测输出被异常拉平 —— 这是一类极难察觉的假阴性。
    # 2) 观测点放在**下一个沿之前 1ns**（即 #8 之后），
    #    这样寄存输出与组合输出的差异才会暴露出来（见 compare_traces）。
    if is_seq:
        pre, settle, advance = "      #1;\n", "      #8;\n", "      @(posedge clk);\n"
    else:
        pre, settle, advance = "", "      #1;\n", ""

    loop_body = (
        "    for (idx = 0; idx < NSTIM; idx = idx + 1) begin\n"
        f"{pre}"
        "      in_vec = stim[idx];\n"
        f"{slice_src}"
        f"{settle}"
        '      $display("VLAB %0d %0b %0b %0b", idx, in_vec, dut_bus, ref_bus);\n'
        f"{advance}"
        "    end\n"
    )
    watchdog = (len(stimuli) + 16) * 12 * (2 if is_seq else 1)

    return TB_HEADER.format(
        nstim=len(stimuli), inw=in_width, clock_decl=clock_decl,
        input_decls=input_decls, output_decls=output_decls_decls,
        dut_mod=dut_module, ref_mod=ref_module,
        conn=", ".join(conn_parts), conn2=", ".join(conn2_parts),
        reset_seq=reset_seq, loop_body=loop_body, prime=slice_src, watchdog=watchdog,
    )


# --------------------------------------------------------------------- 轨迹解析
_TRACE_RE = re.compile(r"^\s*VLAB\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", re.M)


@dataclass
class Trace:
    index: list[int] = field(default_factory=list)
    din: list[str] = field(default_factory=list)
    dut: list[str] = field(default_factory=list)
    ref: list[str] = field(default_factory=list)
    done: bool = False
    timeout: bool = False


def parse_trace(text: str) -> Trace:
    t = Trace()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("VLAB DONE"):
            t.done = True
        elif line.startswith("VLAB TIMEOUT"):
            t.timeout = True
        else:
            m = _TRACE_RE.match(line)
            if m:
                t.index.append(int(m.group(1)))
                t.din.append(m.group(2))
                t.dut.append(m.group(3))
                t.ref.append(m.group(4))
    return t


# --------------------------------------------------------------------- 比对
@dataclass
class CompareResult:
    total: int = 0
    matched: int = 0
    mismatched: int = 0
    x_events: int = 0
    first_mismatch: dict | None = None
    witnesses: list[dict] = field(default_factory=list)
    best_lag: int = 0
    lag_matched: int = 0
    timed_out: bool = False

    @property
    def pass_rate(self) -> float:
        return self.matched / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total, "matched": self.matched, "mismatched": self.mismatched,
            "pass_rate": round(self.pass_rate, 4), "x_events": self.x_events,
            "best_lag": self.best_lag, "lag_matched": self.lag_matched,
            "first_mismatch": self.first_mismatch, "timed_out": self.timed_out,
        }


def _has_x(s: str) -> bool:
    return "x" in s.lower() or "z" in s.lower()


def compare_traces(t: Trace, max_lag: int = 3, witness_limit: int = 5) -> CompareResult:
    """逐周期比对；同时做 lag 移位重比对以识别「只差一拍」的实现。"""
    r = CompareResult(total=len(t.index), timed_out=t.timeout)
    if r.total == 0:
        return r

    for i in range(r.total):
        d, g = t.dut[i], t.ref[i]
        if _has_x(d) or _has_x(g):
            r.x_events += 1
            # X 只在未复位或实现不完整时出现，记为失配而非通过
            if r.mismatched == 0 and len(r.witnesses) < witness_limit:
                r.witnesses.append({"idx": i, "in": t.din[i], "dut": d, "ref": g, "kind": "X"})
            r.mismatched += 1
            continue
        if d == g:
            r.matched += 1
        else:
            r.mismatched += 1
            if len(r.witnesses) < witness_limit:
                r.witnesses.append({"idx": i, "in": t.din[i], "dut": d, "ref": g, "kind": "VALUE"})
            if r.first_mismatch is None:
                r.first_mismatch = r.witnesses[0]

    # 延迟错位检测：把两条轨迹做 ±L 拍的相对平移后重比对。
    # 双向都要看 —— 实现既可能比参考「晚一拍」（多打了一级流水），
    # 也可能「早一拍」（Mealy 型直接组合输出，而参考是寄存输出）。
    best = r.pass_rate
    for off in [o for o in range(-max_lag, max_lag + 1) if o != 0]:
        idx_range = range(r.total - off) if off > 0 else range(-off, r.total)
        hit = usable = 0
        for i in idx_range:
            d, g = t.dut[i + off], t.ref[i]
            if _has_x(d) or _has_x(g):
                continue
            usable += 1
            if d == g:
                hit += 1
        if usable:
            rate = hit / usable
            if rate > best:
                best, r.best_lag, r.lag_matched = rate, off, hit
    return r


# --------------------------------------------------------------------- 失败分类
FAILURE_TAXONOMY = {
    "SYNTAX":         "编译失败：语法错误、未声明信号、非法连接",
    "INTERFACE":      "接口违规：module 名/端口名/方向/位宽与规格不符，或使用了被禁的 parameter",
    "LATCH":          "推断出锁存器：组合逻辑分支不完整，综合后出现电平敏感器件",
    "TIMEOUT":        "仿真超时：可能存在组合反馈环或缺少 $finish 之外的终止条件",
    "RESET":          "复位异常：释放复位后输出仍为不定态 X，或未按规格响应复位",
    "TIMING_SHIFT":   "时序错位：逻辑基本正确但输出比参考晚 N 拍",
    "VALUE_MISMATCH": "功能错误：存在使输出与参考不一致的输入向量",
    "SPEC_REFUSED":   "规格不足以唯一确定行为，智能体应当拒绝实现而非猜测",
}


@dataclass
class Verdict:
    ok: bool
    stage: str
    failure_class: str | None = None
    detail: str = ""
    evidence: list[str] = field(default_factory=list)

    def explain(self) -> str:
        if self.ok:
            return f"[{self.stage}] PASS"
        return f"[{self.stage}] {self.failure_class}: {self.detail}"


def _error_lines(text: str, limit: int = 8) -> list[str]:
    """从编译器输出里挑出**真正的错误行**。

    直接截断原文会踩一个大坑：iverilog 的输出开头常常是几行 `timescale ... inherited`
    之类与失败无关的 warning，截断后喂给模型的就只剩下这些噪音，真正的
    `'light' has already been declared` 反而没传过去——修复自然永远修不好。
    这里只保留含 error 的行，并把绝对路径压缩成文件名，让证据短而准。
    """
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "error" not in low and "syntax" not in low:
            continue
        # `C:\\...\\foo.v:7: error: ...` -> `foo.v:7: error: ...`
        m = re.match(r"^[A-Za-z]:[\\/](?:[^\\/]+[\\/])*([^\\/]+?):(\d+):\s*(.*)$", line)
        if m:
            line = f"{m.group(1)}:{m.group(2)}: {m.group(3)}"
        out.append(line[:200])
        if len(out) >= limit:
            break
    return out or [(text or "").strip()[:400]]


def classify(compile_res, iface_diff: InterfaceDiff, trace: Trace, cmp_res: CompareResult,
             cells: dict, is_sequential: bool) -> Verdict:
    """按「编译 → 接口 → 综合 → 仿真 → 比对」的顺序归因。

    注意：越靠前的检查优先级越高，因为它拦住了后续所有证据的可靠性。
    """
    if not compile_res.ok:
        return Verdict(False, "compile", "SYNTAX", compile_res.tail(12) or "编译失败",
                       _error_lines(compile_res.stderr, limit=8))

    if not iface_diff.ok:
        return Verdict(False, "interface", "INTERFACE", "; ".join(iface_diff.problems[:4]),
                       iface_diff.problems)

    latches = cells.get("$dlatch", 0) + sum(v for k, v in cells.items() if "dlatch" in k.lower())
    if not is_sequential and latches > 0:
        return Verdict(False, "synthesis", "LATCH",
                       f"综合后推断出 {latches} 个锁存器（组合逻辑不应有电平敏感器件）",
                       [f"{k}={v}" for k, v in cells.items() if k != "__total__"])

    if trace.timeout or (cmp_res.total == 0 and not trace.done):
        return Verdict(False, "simulation", "TIMEOUT", "仿真未在预期时间内完成", [])

    if cmp_res.total == 0:
        return Verdict(False, "simulation", "SYNTAX", "测试台未产生任何采样点", ["请检查是否缺少输出信号"])

    if is_sequential and cmp_res.x_events > cmp_res.total * 0.3:
        return Verdict(False, "comparison", "RESET",
                       f"{cmp_res.x_events}/{cmp_res.total} 个周期出现不定态 X，疑似复位未生效",
                       [str(w) for w in cmp_res.witnesses[:3]])

    if cmp_res.mismatched == 0:
        return Verdict(True, "comparison", None, "", [])

    if cmp_res.best_lag != 0 and cmp_res.lag_matched / max(1, cmp_res.total) >= 0.9:
        direction = "滞后" if cmp_res.best_lag > 0 else "超前"
        return Verdict(False, "comparison", "TIMING_SHIFT",
                       f"输出相对参考{direction} {abs(cmp_res.best_lag)} 拍，"
                       f"平移对齐后命中 {cmp_res.lag_matched}/{cmp_res.total}，"
                       f"判定为节拍错位而非逻辑错误",
                       [str(w) for w in cmp_res.witnesses[:3]])

    return Verdict(False, "comparison", "VALUE_MISMATCH",
                   f"{cmp_res.mismatched}/{cmp_res.total} 个向量与参考不一致",
                   [str(w) for w in cmp_res.witnesses[:3]])
