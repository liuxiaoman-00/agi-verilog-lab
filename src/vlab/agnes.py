"""Agnes 模型接入层。

赛事要求「所有模型调用仅限 Agnes 模型」（通知正文口径），因此本项目**只有一个模型供应商**。
这里把它封装成一个带完整容错的最小客户端：

    超时 → 指数退避重试（2s / 4s / 8s ...）→ 全部失败则抛出 ModelCallError

每一次调用都会写进 journal，连同时延与 token 用量。
这份 journal 就是提交材料里「Agnes 模型参与核心任务证据」的原始素材。

为什么不用 requests？
    为了复现成本最低：评委拿到仓库后 `pip install -r requirements.txt` 只需要装
    matplotlib 之类的可选组件，核心链路零第三方依赖即可跑通。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path

# 中国站网关（AGH 源码 agnes-ai.ts 确认：国际站 apihub.agnes-ai.com 拒绝中国 Key）
DEFAULT_BASE_URL = "https://api.agnes-ai.cn/v1"
DEFAULT_MODEL = os.environ.get("AGNES_MODEL", "agnes-3.0-flash")

# 密钥文件的候选位置（按顺序找，第一个非空的有效）。
# 支持读取文件是为了**录屏/演示安全**：这样命令行历史与画面里都不会出现明文密钥。
def _key_file_candidates() -> list[Path]:
    here = Path(__file__).resolve().parents[2]  # 项目根
    return [
        Path.home() / ".agnes_key",
        here / ".agnes_key",
        here / "agnes.key",
    ]


def _resolve_api_key() -> str:
    """按 环境变量 → 密钥文件 的顺序解析密钥，都没有则返回空字符串。"""
    env = os.environ.get("AGNES_API_KEY", "").strip()
    if env:
        return env
    for cand in _key_file_candidates():
        try:
            if cand.is_file():
                value = cand.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except OSError:
            continue
    return ""


class ModelCallError(RuntimeError):
    """模型调用最终失败。"""


@dataclass
class ModelCall:
    purpose: str
    model: str
    ok: bool
    seconds: float
    error: str = ""
    prompt_chars: int = 0
    completion_chars: int = 0
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class AgnesClient:
    """Agnes 文本模型客户端（OpenAI chat/completions 兼容协议）。"""

    def __init__(self, api_key: str | None = None, base_url: str = DEFAULT_BASE_URL,
                 model: str = DEFAULT_MODEL, timeout: int = 120, max_retries: int = 4,
                 journal_path: Path | None = None) -> None:
        self.api_key = api_key or _resolve_api_key()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.journal_path = journal_path
        self.journal: list[dict] = []

    # ------------------------------------------------------------------ 内部
    def _record(self, call: ModelCall) -> None:
        self.journal.append(call.to_dict())
        if self.journal_path:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(call.to_dict(), ensure_ascii=False) + "\n")

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------------ 对外
    def chat(self, prompt: str, system: str = "", purpose: str = "generic",
             temperature: float = 0.2, max_tokens: int = 2048) -> str:
        """调用一次文本模型，失败按指数退避重试。"""
        if not self.api_key:
            raise ModelCallError(
                "未配置 Agnes API Key。请设置环境变量 AGNES_API_KEY，"
                "或从 platform.agnes-ai.com 控制台创建 Token Plan Key。"
            )
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }

        last_err = ""
        for attempt in range(self.max_retries):
            t0 = time.time()
            try:
                data = self._post(payload)
                text = data["choices"][0]["message"]["content"]
                self._record(ModelCall(purpose, self.model, True, time.time() - t0,
                                       prompt_chars=len(prompt), completion_chars=len(text),
                                       usage=data.get("usage", {})))
                return text
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                last_err = f"HTTP {exc.code}: {body}"
                retryable = exc.code in (408, 409, 429) or 500 <= exc.code < 600
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                retryable = True

            if not retryable or attempt == self.max_retries - 1:
                break
            wait = 2.0 * (2 ** attempt)
            time.sleep(wait)

        self._record(ModelCall(purpose, self.model, False, 0.0, error=last_err,
                               prompt_chars=len(prompt)))
        raise ModelCallError(f"Agnes 调用失败（已重试 {self.max_retries} 次）：{last_err}")


# --------------------------------------------------------------------- 输出清洗
_FENCE_RE = re.compile(r"```(?:verilog|v|systemverilog|sv)?\s*\n(.*?)```", re.S | re.I)


def extract_verilog(text: str) -> str:
    """从模型输出里提取纯 Verilog 源码。

    模型几乎总是用 ```verilog 代码块包裹代码，而编译器只认裸代码。
    这里依次尝试：代码块 -> 首个 module 起到 endmodule -> 原文。
    """
    blocks = _FENCE_RE.findall(text)
    if blocks:
        best = max(blocks, key=len)
        if "module" in best:
            return best.strip()

    m = re.search(r"(\bmodule\b.*?\bendmodule\b)", text, re.S)
    if m:
        return m.group(1).strip()
    return text.strip()


def first_json_object(text: str) -> dict:
    """从输出里抠出第一个 JSON 对象，容忍前后有解释文字。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def audit_extract_verilog(text: str) -> str:
    """audit agent"""
    return extract_verilog(text)
