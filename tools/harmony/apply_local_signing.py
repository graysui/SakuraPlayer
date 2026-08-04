#!/usr/bin/env python3
"""TASK-301: HarmonyOS 签名密码本地化工具。

DevEco Studio 自动签名会把 keyPassword/storePassword（加密混淆值）写入
harmony/build-profile.json5。本项目安全边界要求签名密码不进入 Git，因此：

- 真实密码保存在本机 harmony/.local/signing.json5（已被 harmony/.gitignore 忽略）。
- 提交到 Git 的 harmony/build-profile.json5 中两个密码字段为空字符串。

用法：
  python tools/harmony/apply_local_signing.py apply   # 用 .local/signing.json5 填充密码后构建
  python tools/harmony/apply_local_signing.py strip   # 提交前清空密码字段（还原脱敏状态）
  python tools/harmony/apply_local_signing.py check   # 检查当前状态与本地密码文件

本脚本不输出、不记录任何密码值。
"""

import json
import re
import sys
from pathlib import Path

HARMONY = Path(__file__).resolve().parents[2] / "harmony"
BUILD_PROFILE = HARMONY / "build-profile.json5"
LOCAL_SIGNING = HARMONY / ".local" / "signing.json5"
PASSWORD_FIELDS = ("keyPassword", "storePassword")


def load_local() -> dict:
    if not LOCAL_SIGNING.exists():
        sys.exit(f"错误：未找到本机签名密码文件 {LOCAL_SIGNING}；请在 DevEco Studio 的 "
                 "File > Project Structure > Signing Configs 中重新生成签名。")
    data = json.loads(LOCAL_SIGNING.read_text(encoding="utf-8"))
    missing = [f for f in PASSWORD_FIELDS if not data.get(f)]
    if missing:
        sys.exit(f"错误：{LOCAL_SIGNING} 缺少字段 {missing}。")
    return data


def read_profile() -> str:
    return BUILD_PROFILE.read_text(encoding="utf-8")


def write_profile(text: str) -> None:
    BUILD_PROFILE.write_text(text, encoding="utf-8")


def replace_password(text: str, field: str, value: str) -> str:
    pattern = re.compile(rf'("{field}":\s*")[^"]*(")')
    new, count = pattern.subn(rf"\g<1>{value}\g<2>", text)
    if count != 1:
        sys.exit(f"错误：build-profile.json5 中 {field} 字段匹配到 {count} 处（应为 1）。")
    return new


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    command = sys.argv[1]
    text = read_profile()
    if command == "apply":
        local = load_local()
        for field in PASSWORD_FIELDS:
            text = replace_password(text, field, local[field])
        write_profile(text)
        print("已用 .local/signing.json5 填充签名密码，可以构建。")
    elif command == "strip":
        for field in PASSWORD_FIELDS:
            text = replace_password(text, field, "")
        write_profile(text)
        print("已清空 build-profile.json5 的签名密码字段，可以提交。")
    elif command == "check":
        local = load_local()
        for field in PASSWORD_FIELDS:
            in_profile = re.search(rf'"{field}":\s*"([^"]*)"', text).group(1)
            state = "已填充" if in_profile else "为空"
            print(f"{field}: profile={state}, local={'存在' if local.get(field) else '缺失'}")
    else:
        sys.exit(f"未知命令：{command}\n{__doc__}")


if __name__ == "__main__":
    main()
