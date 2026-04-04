# Orbit CLI 使用示例

## 安装

```bash
cd /path/to/orbit-repo
pip install -e .
```

## 基本使用

### 查看帮助

```bash
# 主帮助
orbit --help

# Gateway 命令帮助
orbit gateway --help

# 版本信息
orbit --version
```

### Gateway 命令

```bash
# 运行 Gateway
orbit gateway run --port 18790

# 查看状态
orbit gateway status

# 调用 Gateway RPC 方法
orbit gateway call health
orbit gateway call health --params '{"key": "value"}'

# 发现 Gateway
orbit gateway discover

# 探测 Gateway
orbit gateway probe --url ws://127.0.0.1:18790

# JSON 输出
orbit gateway status --json
orbit gateway call health --json
```

## 开发模式

```bash
# 使用开发配置
orbit --dev gateway run
```

## 命令结构

```
orbit
├── gateway
│   ├── run          # 运行 Gateway
│   ├── status       # 查看状态
│   ├── call         # 调用 RPC 方法
│   ├── health       # 健康检查
│   ├── discover     # 发现 Gateway
│   └── probe        # 探测 Gateway
└── (未来更多命令...)
```

## 扩展命令示例

参考 `ARCHITECTURE.md` 了解如何添加新命令。
