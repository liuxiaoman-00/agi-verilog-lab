# -*- coding: utf-8 -*-
"""AGH / MCP 的 stdio 入口 —— 供 `agh mcp add vlab-verifier --stdio python --args ...` 调用。

独立成一个文件，是为了让 AGH 只需要「一个可执行文件 + 一个参数」就能拉起服务，
不必依赖调用方的 PYTHONPATH 或工作目录。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from vlab.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
