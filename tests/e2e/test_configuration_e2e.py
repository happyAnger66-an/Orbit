import json
import os
from pathlib import Path

import pytest

from mw4agent.cli.main import main as cli_main


def _run_cli(argv: list[str]) -> None:
    # 调用 CLI entrypoint，argv 第一个元素为程序名
    cli_main(argv)


@pytest.mark.parametrize("use_encryption", [False, True])
def test_configuration_set_llm_updates_root_config(tmp_path, monkeypatch, use_encryption):
    """E2E: configuration set-llm 写入 ~/.mw4agent/mw4agent.json（支持加密/明文两种路径）."""

    # 将 HOME 指到临时目录，避免污染真实环境
    monkeypatch.setenv("HOME", str(tmp_path))

    # 控制是否启用加密
    if use_encryption:
        monkeypatch.delenv("MW4AGENT_IS_ENC", raising=False)
        # 提供一个虚拟但合法的密钥
        monkeypatch.setenv("MW4AGENT_SECRET_KEY", base64_key := "dGVzdC1zZWNyZXQta2V5LTIzNDU2Nzg5MDEyMzQ1Ng==")
    else:
        monkeypatch.setenv("MW4AGENT_IS_ENC", "0")
        monkeypatch.delenv("MW4AGENT_SECRET_KEY", raising=False)

    provider = "vllm"
    model_id = "test-model"
    base_url = "http://127.0.0.1:8000"
    api_key = "secret-key"

    _run_cli(
        [
            "mw4agent",
            "configuration",
            "set-llm",
            "--provider",
            provider,
            "--model-id",
            model_id,
            "--base-url",
            base_url,
            "--api-key",
            api_key,
        ]
    )

    cfg_path = Path(tmp_path) / ".mw4agent" / "mw4agent.json"
    assert cfg_path.exists()

    # 配置文件在启用加密时会被加密存储，这里只关心通过 CLI 再读出来是否正确。
    # 直接调用 CLI: configuration show --json
    from io import StringIO
    import sys

    buf = StringIO()
    monkeypatch.setattr(sys, "stdout", buf)

    _run_cli(["mw4agent", "configuration", "show", "--json"])

    output = buf.getvalue()
    data = json.loads(output)

    assert data["llm"]["provider"] == provider
    assert data["llm"]["model_id"] == model_id
    assert data["llm"].get("base_url") == base_url
    assert data["llm"].get("api_key") == api_key

