"""EDA 后端：对 iverilog / vvp / yosys 的确定性调用封装。

设计原则
--------
本模块是「工具层」，只做一件事：把 EDA 工具包装成**输入确定 — 输出确定**的函数。
它不含任何模型、不含任何推理逻辑，因此可以离线单元测试，也可以被上层
（AGH 通过 MCP，或本地控制器直接 import）复用。

不变量：
  * 每次调用都在独立的工作目录中进行，避免文件互相污染；
  * 超时、崩溃、工具缺失都被收敛成 ToolResult，绝不向上抛异常；
  * command 字段全程留痕，用于生成「工具调用链」证据。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# oss-cad-suite 解压后的常见布局，用于在没有 PATH 时自动探测
_TOOLBOX_LAYOUT = (
    "oss-cad-suite/bin",
    "oss-cad-suite/lib",
    "bin",
    "lib",
    "py3bin",
)


def _walk_up_for_tools(exe_name: str, levels: int = 6) -> str | None:
    """从当前文件逐级向上寻找 `tools/oss-cad-suite`。

    项目目录可以放在任意位置，工具链也可以解压到任意位置，
    因此这里不做路径硬编码，而是向上遍历若干层去找。
    """
    here = Path(__file__).resolve()
    for i in range(2, min(levels, len(here.parents)) + 2):
        base = here.parents[i - 1] if i - 1 < len(here.parents) else None
        if base is None:
            break
        for sub in _TOOLBOX_LAYOUT:
            cand = base / "tools" / sub / exe_name
            if cand.is_file():
                return str(cand)
    return None


@dataclass
class ToolResult:
    """一次 EDA 工具调用的完整留痕。"""

    tool: str
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    command: list[str] = field(default_factory=list)

    @property
    def output(self) -> str:
        return "\n".join(p for p in (self.stdout.strip(), self.stderr.strip()) if p).strip()

    def tail(self, n: int = 30) -> str:
        lines = self.output.splitlines()
        return "\n".join(lines[-n:]) if len(lines) > n else self.output

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "returncode": self.returncode,
            "command": self.command,
            "stdout_len": len(self.stdout),
            "stderr_len": len(self.stderr),
        }


class EDAUnavailable(RuntimeError):
    """EDA 工具不可用时抛出，携带安装指引。"""


class EDABackend:
    """定位并调用 iverilog / vvp / yosys。"""

    def __init__(self, tool_home: str | os.PathLike | None = None, timeout: int = 60) -> None:
        self.tool_home = Path(tool_home) if tool_home else None
        self.timeout = timeout
        self._cache: dict[str, str] = {}

    # ------------------------------------------------------------------ 定位
    def _exe_name(self, base: str) -> str:
        return f"{base}.exe" if os.name == "nt" else base

    def find(self, base: str) -> str | None:
        """按 PATH → tool_home → 相邻 tools 目录的顺序定位可执行文件。"""
        if base in self._cache:
            return self._cache[base] or None
        name = self._exe_name(base)

        found = shutil.which(base)
        if not found and self.tool_home:
            for sub in _TOOLBOX_LAYOUT:
                cand = self.tool_home / sub / name
                if cand.is_file():
                    found = str(cand)
                    break
        if not found:
            found = _walk_up_for_tools(self._exe_name(base)) or None
            # Windows 下 oss-cad-suite 的 DLL 在 lib/ 而不全在 exe 同目录，
            # 必须为子进程把 bin 与 lib 都放进 PATH，否则会以 0xC0000135 直接崩掉。
            if found and self.tool_home is None:
                self.tool_home = Path(found).parent.parent

        self._cache[base] = found or ""
        return found or None

    def discover(self) -> dict[str, str]:
        return {b: (self.find(b) or "") for b in ("iverilog", "vvp", "yosys")}

    def require(self, base: str) -> str:
        p = self.find(base)
        if not p:
            raise EDAUnavailable(
                f"未找到 {base}。请把 oss-cad-suite 解压到本地并设置 tool_home，"
                f"或将其 bin 目录加入 PATH。建议：解压 tools/oss-cad-suite-windows-x64.tgz"
            )
        return p

    # ------------------------------------------------------------------ 环境
    def env(self) -> dict[str, str]:
        """构造子进程环境。Windows 下 oss-cad-suite 需要 bin/lib 参与 DLL 搜索。"""
        e = os.environ.copy()
        if self.tool_home:
            extra = [str(self.tool_home / s) for s in _TOOLBOX_LAYOUT if (self.tool_home / s).is_dir()]
            if extra:
                e["PATH"] = os.pathsep.join(extra) + os.pathsep + e.get("PATH", "")
        return e

    # ------------------------------------------------------------------ 执行
    def run(self, args: list[str], cwd: Path | None = None, tool: str = "shell") -> ToolResult:
        """执行一条命令并把全部结果收敛成 ToolResult。"""
        try:
            proc = subprocess.run(
                args,
                cwd=str(cwd) if cwd else None,
                env=self.env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                # 关键：必须切断 stdin。yosys 在脚本执行出错（例如 hierarchy -check 失败）
                # 时会回落到交互模式去读命令，如果不给它一个立刻关闭的 stdin，
                # 子进程会永久挂住，表现为整个流水线“神秘卡死”。
                stdin=subprocess.DEVNULL,
            )
            return ToolResult(tool, proc.returncode == 0, proc.returncode, proc.stdout, proc.stderr, args)
        except subprocess.TimeoutExpired as exc:
            return ToolResult(tool, False, -1, exc.stdout or "", f"TIMEOUT after {self.timeout}s", args)
        except OSError as exc:
            return ToolResult(tool, False, -2, "", f"OS error: {exc}", args)

    # ------------------------------------------------------------------ 语法层
    def compile(self, sources: list[Path], out: Path, workdir: Path, top: str | None = None,
                defines: dict[str, str] | None = None) -> ToolResult:
        """iverilog 编译。返回 ok=True 表示语法与端口连接均无错。"""
        iverilog = self.require("iverilog")
        args = [iverilog, "-Wall", "-Winfloop", "-g2012", "-o", str(out)]
        for k, v in (defines or {}).items():
            args += ["-D", f"{k}={v}"]
        args += [str(s) for s in sources]
        r = self.run(args, cwd=workdir, tool="iverilog")
        r.stdout = r.stdout or ""
        return r

    def simulate(self, vvp_out: Path, workdir: Path) -> ToolResult:
        """vvp 执行仿真。"""
        vvp = self.require("vvp")
        r = self.run([vvp, str(vvp_out)], cwd=workdir, tool="vvp")
        return r

    def synth(self, sources: list[Path], top: str, workdir: Path) -> ToolResult:
        """yosys 综合并输出 cell 统计，用于**结构侧**验证。

        这里刻意只跑到 `proc; opt; stat` 而不再 `techmap`：
        过早映射到门级会把 `$dlatch` 拆散成底层原语，反而丢失「推断出锁存器」
        这一最重要的可诊断信号。保留语义级 cell（$add / $mux / $dlatch / $dff）
        也让面积代理指标更稳定可比。
        """
        yosys = self.require("yosys")
        script = f"""
read_verilog {' '.join(str(s) for s in sources)}
hierarchy -check -top {top}
proc
opt
stat
"""
        args = [yosys, "-Q", "-p", script]
        r = self.run(args, cwd=workdir, tool="yosys")
        return r


# --------------------------------------------------------------------- 解析辅助
# yosys 0.6x `stat` 的实际排版是「数量在前、单元名在后」，例如：
#        3 cells
#        1   $eq
_CELL_RE = re.compile(r"^\s*(\d+)\s+(\$\w+)\s*$", re.M)
_CELL_COUNT_RE = re.compile(r"^\s*(\d+)\s+cells\b", re.M)


def parse_cells(stat_output: str) -> dict[str, int]:
    """从 yosys `stat` 输出里抽取各 cell 类型的数量。"""
    cells: dict[str, int] = {}
    m = _CELL_COUNT_RE.search(stat_output)
    if m:
        cells["__total__"] = int(m.group(1))
    for cnt, name in _CELL_RE.findall(stat_output):
        cells[name] = cells.get(name, 0) + int(cnt)
    return cells


def latch_count(cells: dict[str, int]) -> int:
    """推断出的锁存器数量（含 const-value latch）。"""
    return sum(v for k, v in cells.items() if "dlatch" in k.lower() or "dlatch" in k)


def flop_count(cells: dict[str, int]) -> int:
    return sum(v for k, v in cells.items() if re.search(r"\$(?:dff|sdff|adff|adffe|sdffce)", k) or
               re.search(r"dff", k, re.I))
