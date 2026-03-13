# MW4Agent CLI 使用示例

## 安装

```bash
cd /home/wujie/sources/opensrc/mw4agent
pip install -e .
```

## 基本使用

### 查看帮助

```bash
# 主帮助
mw4agent --help

# Gateway 命令帮助
mw4agent gateway --help

# 版本信息
mw4agent --version
```

### Gateway 命令

```bash
# 运行 Gateway
mw4agent gateway run --port 18790

# 查看状态
mw4agent gateway status

# 调用 Gateway RPC 方法
mw4agent gateway call health
mw4agent gateway call health --params '{"key": "value"}'

# 发现 Gateway
mw4agent gateway discover

# 探测 Gateway
mw4agent gateway probe --url ws://127.0.0.1:18790

# JSON 输出
mw4agent gateway status --json
mw4agent gateway call health --json
```

## 开发模式

```bash
# 使用开发配置
mw4agent --dev gateway run
```

## 命令结构

```
mw4agent
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
