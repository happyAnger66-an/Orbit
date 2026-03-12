import asyncio
import socket
from typing import Any, Dict

import pytest

from mw4agent.channels.plugins.feishu import FeishuChannel
from mw4agent.channels.types import InboundContext


def _find_free_port() -> int:
    """Find an available TCP port on localhost for tests."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.asyncio
async def test_feishu_deliver_prints_without_chat_id(monkeypatch, capsys):
    channel = FeishuChannel()

    # 构造一个最小的 InboundContext 和 OutboundPayload.extra 结构
    from mw4agent.channels.types import OutboundPayload

    payload = OutboundPayload(
        text="hello",
        is_error=False,
        extra={"inbound": {"extra": {}}},
    )

    await channel.deliver(payload)
    captured = capsys.readouterr()
    assert "[feishu:AI] hello" in captured.out


@pytest.mark.asyncio
async def test_feishu_run_monitor_url_verification(monkeypatch):
    """简单验证 run_monitor 调用 webhook 分支时不会抛异常。

    为避免在测试中真正启动 uvicorn HTTP server，这里通过 monkeypatch
    将 `_run_webhook_monitor` 替换为一个快速返回的协程。这样可以验证
    分支选择和调用链路，而不会因为端口冲突或阻塞 server 导致测试挂死。
    """
    # Use a free port to avoid clashes if code ever inspects it.
    port = _find_free_port()
    channel = FeishuChannel(host="127.0.0.1", port=port, path="/feishu/test-webhook")

    async def fake_on_inbound(ctx: InboundContext) -> None:  # pragma: no cover
        pass

    async def fake_run_webhook_monitor(self, *, on_inbound):  # pragma: no cover
        # Simulate a tiny bit of async work, then return.
        await asyncio.sleep(0)

    # Patch the class method so that any FeishuChannel.run_monitor uses the fake monitor.
    from mw4agent.channels.plugins.feishu import FeishuChannel as FeishuChannelClass
    monkeypatch.setattr(FeishuChannelClass, "_run_webhook_monitor", fake_run_webhook_monitor, raising=True)

    # Just ensure run_monitor completes without raising.
    try:
        await asyncio.wait_for(channel.run_monitor(on_inbound=fake_on_inbound), timeout=0.5)
    except Exception as e:
        pytest.fail(f"FeishuChannel.run_monitor raised unexpectedly: {e}")

