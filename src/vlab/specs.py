"""规格库：题目描述 + 接口契约 + 激励策略。

规格（spec）是本项目里唯一的人工输入，也是整个闭环的锚点：
    * 它声明了严格的接口契约（module 名、端口、方向、位宽）；
    * 它决定了激励策略（穷举 / 边界+随机）；
    * 它指向一份人工参考实现 golden 模块。

只要规格明确，「AI 写得对不对」就不再依赖人的主观判断，而由工具自动裁决。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]          # .../agi-verilog-lab
SPEC_DIR = _ROOT / "benchmarks"


def project_root() -> Path:
    return _ROOT


@dataclass
class Spec:
    id: str
    title: str
    description: str
    module: str
    kind: str                       # combinational | sequential
    ports: list[dict]
    stimulus: dict = field(default_factory=dict)
    clock: str = "clk"
    reset: str | None = None
    reset_active: str = "low"
    difficulty: str = "medium"
    tags: list[str] = field(default_factory=list)

    @property
    def golden_module(self) -> str:
        return f"{self.module}_golden"

    @property
    def data_port_spec(self) -> list[dict]:
        """非时钟、非复位的输入端口。"""
        return [p for p in self.ports
                if p["direction"] == "input" and p["name"] not in (self.clock, self.reset)]

    @property
    def data_input_width(self) -> int:
        return sum(int(p.get("width", 1)) for p in self.data_port_spec)

    @property
    def is_sequential(self) -> bool:
        return self.kind == "sequential"


def load_specs(path: Path | str | None = None) -> list[Spec]:
    p = Path(path) if path else SPEC_DIR / "specs.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [Spec(**{k: v for k, v in item.items()}) for item in raw]


def get_spec(specs: list[Spec], sid: str) -> Spec | None:
    for s in specs:
        if s.id == sid:
            return s
    return None


def golden_path(spec: Spec) -> Path:
    return SPEC_DIR / "golden" / f"{spec.module}.v"
