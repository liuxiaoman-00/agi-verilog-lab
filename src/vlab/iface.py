"""模块接口解析与比对。

为什么要自己解析端口？
    因为这个项目的核心命题是「**不依赖人工测试**地完成验证」。
    验证引擎必须在不知道实现细节的前提下，仅凭**规格声明的接口**去自动搭建
    等价性测试台。所以要先把 AI 写出来的模块接口解析出来，逐项与规格比对：

        module 名 / 端口名 / 方向 / 位宽 / 是否引入 parameter

    只要有一项不符，就判定为 `INTERFACE` 类失败 —— 这是一类**真实且高频**的工程错误，
    （历史上大量 HDL 集成 bug 来自接口不一致），也是很好的失败分类素材。

支持两种书写风格：
    * ANSI：`module m(input [3:0] a, output reg y);`
    * 非 ANSI：`module m(a, y); input [3:0] a; output y; endmodule`
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Port:
    name: str
    direction: str                      # input | output | inout
    high: int = 0
    low: int = 0
    declared_width: str = ""            # 原始写法，例如 "[3:0]"

    @property
    def width(self) -> int:
        return abs(self.high - self.low) + 1

    def to_dict(self) -> dict:
        return {"name": self.name, "direction": self.direction, "width": self.width,
                "declared": self.declared_width}


@dataclass
class ModuleInfo:
    name: str
    ports: list[Port] = field(default_factory=list)
    has_parameter: bool = False
    parse_note: str = ""

    @property
    def inputs(self) -> list[Port]:
        return [p for p in self.ports if p.direction == "input"]

    @property
    def outputs(self) -> list[Port]:
        return [p for p in self.ports if p.direction in ("output", "inout")]

    def get(self, name: str) -> Port | None:
        for p in self.ports:
            if p.name == name:
                return p
        return None

    def to_dict(self) -> dict:
        return {"name": self.name, "has_parameter": self.has_parameter,
                "ports": [p.to_dict() for p in self.ports], "note": self.parse_note}


# --------------------------------------------------------------------- 文本清理
def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _balanced(text: str, start: int) -> tuple[str, int]:
    """从 text[start] == '(' 起，取出配对的括号内容与结束下标。"""
    assert text[start] == "("
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return text[start + 1: i], i + 1
        i += 1
    raise ValueError("括号未闭合")


# --------------------------------------------------------------------- 声明解析
_DECL_RE = re.compile(
    r"\b(input|output|inout)\b"                       # 方向
    r"(?:\s+(?:wire|reg|logic|signed|unsigned))*"
    r"(?:\s*\[\s*(\d+)\s*:\s*(\d+)\s*\])?"            # 可选位宽
    r"\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)"      # 一个或多个端口名
    r"\s*(?:,|;|\)|$)"
)


def _parse_declarations(block: str) -> list[Port]:
    ports: list[Port] = []
    for m in _DECL_RE.finditer(block):
        direction = m.group(1)
        high = int(m.group(2)) if m.group(2) else 0
        low = int(m.group(3)) if m.group(3) else 0
        declared = f"[{high}:{low}]" if m.group(2) else ""
        for raw in m.group(4).split(","):
            name = raw.strip()
            if name and not _looks_like_reserved(name):
                ports.append(Port(name, direction, high, low, declared))
    return ports


_RESERVED = {
    "always", "assign", "begin", "end", "case", "default", "module", "endmodule",
    "wire", "reg", "integer", "genvar", "generate", "endgenerate", "posedge",
    "negedge", "if", "else", "for", "while", "initial", "parameter", "localparam",
}


def _looks_like_reserved(name: str) -> bool:
    return name.lower() in _RESERVED


# --------------------------------------------------------------------- 顶层入口
def parse_module(source: str | Path) -> ModuleInfo:
    """解析第一个 module 的接口信息。解析失败时返回 note 说明原因，不抛异常。"""
    text = source if isinstance(source, str) else source.read_text(encoding="utf-8", errors="replace")
    text = strip_comments(text)

    m = re.search(r"\bmodule\s+([A-Za-z_]\w*)", text)
    if not m:
        return ModuleInfo(name="", parse_note="未找到 module 声明")

    name = m.group(1)
    idx = m.end()
    has_parameter = False
    body_offset = idx

    # 处理可选的 `#(...)` 参数块
    after_name = text[idx:]
    lead = len(after_name) - len(after_name.lstrip())
    rest = after_name[lead:]
    if rest.startswith("#"):
        has_parameter = True
        paren = lead + after_name[lead:].index("(")
        try:
            _content, end = _balanced(after_name, paren)
            body_offset = idx + end
        except ValueError:
            return ModuleInfo(name=name, has_parameter=True, parse_note="parameter 块括号未闭合")

    tail = text[body_offset:]
    k2 = len(tail) - len(tail.lstrip())

    ports: list[Port] = []
    if k2 < len(tail) and tail[k2] == "(":
        try:
            port_block, end = _balanced(tail, k2)
        except ValueError:
            return ModuleInfo(name=name, has_parameter=has_parameter, parse_note="端口列表括号未闭合")
        after_ports = tail[end:]

        if re.search(r"\b(input|output|inout)\b", port_block):
            ports = _parse_declarations(port_block + " ;")
        else:
            # 非 ANSI：端口名列表 + 体内方向声明
            names = [n.strip() for n in port_block.split(",") if n.strip()]
            endmod = after_ports.find("endmodule")
            scope = after_ports[: endmod if endmod > 0 else len(after_ports)]
            body_ports = {p.name: p for p in _parse_declarations(scope)}
            for nm in names:
                base = nm.split("[")[0].strip()
                p = body_ports.get(base)
                ports.append(p if p else Port(base, "input", 0, 0, ""))
            return ModuleInfo(name=name, ports=ports, has_parameter=has_parameter,
                              parse_note="" if body_ports else "非ANSI风格且未找到方向声明")
    else:
        return ModuleInfo(name=name, has_parameter=has_parameter, parse_note="未找到端口列表")

    return ModuleInfo(name=name, ports=ports, has_parameter=has_parameter)


# --------------------------------------------------------------------- 接口比对
@dataclass
class InterfaceDiff:
    ok: bool
    problems: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def compare_interface(actual: ModuleInfo, expect: dict) -> InterfaceDiff:
    """把实际接口与规格声明的接口逐项比对。

    expect 形如：
        {"module": "seq1011", "clock": "clk", "reset": "rst_n", "reset_active": "low",
         "ports": [{"name": "x", "direction": "input", "width": 1}, ...]}
    """
    problems: list[str] = []

    if not actual.name:
        problems.append("未能解析出 module 声明")
        return InterfaceDiff(False, problems)

    want_name = expect.get("module")
    if want_name and actual.name != want_name:
        problems.append(f"module 名应为 `{want_name}`，实际为 `{actual.name}`")

    if actual.has_parameter:
        problems.append("规格禁止使用 parameter / `#(...)`，实际检测到参数化接口")

    want_ports = {p["name"]: p for p in expect.get("ports", [])}
    got_ports = {p.name: p for p in actual.ports}

    for nm, spec in want_ports.items():
        if nm not in got_ports:
            problems.append(f"缺失端口 `{nm}`（规格要求 {spec['direction']} width={spec.get('width', 1)}）")
            continue
        got = got_ports[nm]
        if got.direction != spec["direction"]:
            problems.append(f"端口 `{nm}` 方向应为 {spec['direction']}，实际为 {got.direction}")
        w = int(spec.get("width", 1))
        if got.width != w:
            problems.append(f"端口 `{nm}` 位宽应为 {w}，实际为 {got.width}（{got.declared_width or '标量'}）")

    extra = sorted(set(got_ports) - set(want_ports))
    if extra:
        problems.append(f"出现规格外的多余端口：{', '.join(extra)}")

    return InterfaceDiff(not problems, problems)
