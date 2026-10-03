"""一键检测 Agnes Key 是否可用，可用则自动存进电脑环境变量。

用法（在项目目录下运行）：
    python check_key.py
然后按提示，把邮箱里的 Key **原样粘贴**进去回车即可。
"""
import json
import subprocess
import time
import urllib.error
import urllib.request

URL = "https://api.agnes-ai.cn/v1/chat/completions"


def test_key(key: str) -> tuple[bool, str]:
    payload = json.dumps({
        "model": "agnes-2.5-flash",
        "messages": [{"role": "user", "content": "只回复两个字：正常"}],
        "max_tokens": 16,
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, method="POST", headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
        return True, f"模型回答「{text}」，耗时 {time.time() - t0:.1f} 秒"
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        reason = {
            401: "钥匙被拒（无效或格式错误）",
            402: "余额 / 配额 / 订阅校验未通过",
            404: "接口或模型名不存在",
            429: "请求太频繁（限流）",
        }.get(e.code, f"HTTP {e.code}")
        return False, f"{reason}：{body}"
    except Exception as e:
        return False, f"网络或其它错误：{type(e).__name__}: {e}"


def save_key(key: str) -> None:
    """写入用户环境变量（相当于在系统设置里永久添加），对新开的窗口生效。"""
    subprocess.run(["setx", "AGNES_API_KEY", key], capture_output=True)


def main() -> None:
    print("=" * 56)
    print(" Agnes Key 检测工具")
    print("=" * 56)
    print("请打开收到 Key 的【原始邮件】，完整复制 sk- 开头的那串字符")
    key = input("粘贴到这里后按回车 > ").strip()

    if not key.startswith("sk-"):
        print("\n[提醒] 正常的 Key 应该以 sk- 开头，你粘贴的内容可能不完整。")
        if input("仍然要继续检测吗？(y/N) > ").strip().lower() != "y":
            return

    print("\n正在测试，请稍等……")
    ok, msg = test_key(key)
    if ok:
        save_key(key)
        print(f"\n[成功] {msg}")
        print("钥匙已保存进电脑环境变量 AGNES_API_KEY。")
        print("注意：只对【新开】的命令行窗口生效，当前这个窗口不算。")
    else:
        print(f"\n[失败] {msg}")
        print("\n排查建议：")
        print("  1. 确认是从原始邮件复制，而不是照着截图手打（0/O、I/l 易混）")
        print("  2. 确认整串完整复制，首尾没有多空格或少字符")
        print("  3. 若仍失败，去 platform.agnes-ai.com 控制台看这把钥匙的状态，")
        print("     或在参赛群里找客服反馈（提供参赛编号 U104，别发钥匙本身）")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。")
