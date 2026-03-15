# systemd 服务：MW4Agent Gateway

与 OpenClaw 的 `openclaw-gateway.service` 用法类似，用于通过 systemd 自动启动并管理 MW4Agent Gateway。

## 1. 安装服务文件

```bash
sudo cp "$(dirname "$0")/mw4agent-gateway.service" /etc/systemd/system/
sudo systemctl daemon-reload
```

## 2. 可选：创建专用用户与状态目录

若使用单元文件中默认的 `User=mw4agent` / `Group=mw4agent` 和 `WorkingDirectory=/var/lib/mw4agent`，需先创建用户与目录：

```bash
sudo useradd -r -s /bin/false mw4agent
sudo mkdir -p /var/lib/mw4agent
sudo chown mw4agent:mw4agent /var/lib/mw4agent
```

若希望以当前用户运行或使用其他目录，可覆盖单元配置，例如：

```bash
sudo systemctl edit mw4agent-gateway.service
```

在打开的片段中修改或添加，例如：

```ini
[Service]
User=你的用户名
Group=你的用户组
WorkingDirectory=/home/你的用户名/mw4agent-state
ExecStart=/usr/bin/python3 -m mw4agent gateway run --bind 0.0.0.0 --port 18790 --session-file mw4agent.sessions.json
```

保存后执行 `daemon-reload`。

## 3. 启用与启动

```bash
sudo systemctl enable mw4agent-gateway.service
sudo systemctl start mw4agent-gateway.service
```

## 4. 常用命令

| 命令 | 说明 |
|------|------|
| `sudo systemctl status mw4agent-gateway` | 查看状态 |
| `sudo systemctl stop mw4agent-gateway` | 停止 |
| `sudo systemctl restart mw4agent-gateway` | 重启 |
| `journalctl -u mw4agent-gateway -f` | 查看日志 |

## 5. 环境与配置

- 会话文件默认在 `WorkingDirectory` 下的 `mw4agent.sessions.json`；可通过 `--session-file` 在 `ExecStart` 中修改。
- LLM/通道等配置由 mw4agent 的配置机制读取（如 `configuration set-*` 或环境变量），与 systemd 无关；若需为服务单独设置环境变量，可创建 `/etc/default/mw4agent-gateway` 并在单元中增加 `EnvironmentFile=-/etc/default/mw4agent-gateway`（需同时用 `systemctl edit` 添加该行）。
