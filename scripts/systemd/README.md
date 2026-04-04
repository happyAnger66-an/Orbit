# systemd 服务：Orbit Gateway

与 OpenClaw 的 `openclaw-gateway.service` 用法类似，用于通过 systemd 自动启动并管理 Orbit Gateway。

## 安装

```bash
sudo cp "$(dirname "$0")/orbit-gateway.service" /etc/systemd/system/
sudo systemctl daemon-reload
```

## 运行用户与目录

若使用单元文件中默认的 `User=orbit` / `Group=orbit` 和 `WorkingDirectory=/var/lib/orbit`，需先创建用户与目录：

```bash
sudo useradd -r -s /bin/false orbit
sudo mkdir -p /var/lib/orbit
sudo chown orbit:orbit /var/lib/orbit
```

## 覆盖配置

```bash
sudo systemctl edit orbit-gateway.service
```

示例（按实际路径修改）：

```ini
[Service]
WorkingDirectory=/home/你的用户名/orbit-state
ExecStart=/usr/bin/python3 -m orbit gateway run --bind 0.0.0.0 --port 18790 --session-file orbit.sessions.json
```

## 启用与常用命令

```bash
sudo systemctl enable orbit-gateway.service
sudo systemctl start orbit-gateway.service
```

| 命令 | 说明 |
|------|------|
| `sudo systemctl status orbit-gateway` | 查看状态 |
| `sudo systemctl stop orbit-gateway` | 停止 |
| `sudo systemctl restart orbit-gateway` | 重启 |
| `journalctl -u orbit-gateway -f` | 查看日志 |
