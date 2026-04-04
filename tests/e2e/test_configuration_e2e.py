import json
import os
from pathlib import Path

import pytest

from orbit.cli.main import main as cli_main


def _run_cli(argv: list[str]) -> None:
    # 调用 CLI entrypoint，argv 第一个元素为程序名；Click 成功时会 sys.exit(0)
    try:
        cli_main(argv)
    except SystemExit as e:
        if e.code != 0:
            raise


@pytest.mark.parametrize("use_encryption", [False, True])
def test_configuration_set_llm_updates_root_config(tmp_path, monkeypatch, use_encryption):
    """E2E: configuration set-llm 写入 ~/.orbit/orbit.json（支持加密/明文两种路径）."""

    # 将 HOME 指到临时目录，避免污染真实环境
    monkeypatch.setenv("HOME", str(tmp_path))

    # 控制是否启用加密
    if use_encryption:
        monkeypatch.delenv("ORBIT_IS_ENC", raising=False)
        # 提供一个虚拟但合法的密钥
        monkeypatch.setenv("ORBIT_SECRET_KEY", base64_key := "dGVzdC1zZWNyZXQta2V5LTIzNDU2Nzg5MDEyMzQ1Ng==")
    else:
        monkeypatch.setenv("ORBIT_IS_ENC", "0")
        monkeypatch.delenv("ORBIT_SECRET_KEY", raising=False)

    provider = "vllm"
    model_id = "test-model"
    base_url = "http://127.0.0.1:8000"
    api_key = "secret-key"

    _run_cli(
        [
            "orbit",
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

    cfg_path = Path(tmp_path) / ".orbit" / "orbit.json"
    assert cfg_path.exists()

    # 在同一进程中 read_root_config() 会使用已 patch 的 HOME，故可直接读取验证
    from orbit.config import read_root_config

    data = read_root_config()
    assert "llm" in data
    assert data["llm"]["provider"] == provider
    assert data["llm"]["model_id"] == model_id
    assert data["llm"].get("base_url") == base_url
    assert data["llm"].get("api_key") == api_key

