# MW4Agent 加密框架使用文档

## 概述

MW4Agent 提供了一套统一的加密文件存储框架，用于保护所有敏感文件（配置、skills、sessions 等）。框架采用 AES-256-GCM 对称加密算法，提供机密性和完整性保护。

## 设计目标

- **统一加密算法与密钥管理**：所有敏感文件使用相同的加密算法和密钥来源
- **简单易用的 API**：提供 `read_json` / `write_json` 接口，逐步替换裸 `open()` / `read()` / `write()`
- **向后兼容**：支持从明文文件平滑迁移到加密文件

## 加密格式（v1）

文件格式：

1. **文件头**：ASCII 文本 `"MW4AGENT_ENC_v1\n"`（固定 16 字节，可人眼识别）
2. **元数据行**：JSON 格式，包含：
   ```json
   {"alg":"AES-256-GCM","kdf":"env","nonce":"<base64>","tag":"<base64>"}
   ```
3. **密文**：base64 编码的加密内容

## 密钥管理

### 环境变量配置

加密框架从环境变量 `MW4AGENT_SECRET_KEY` 读取密钥。

**推荐方式**：使用 base64 编码的 32 字节随机数：

```bash
# 生成密钥
python3 - << 'PY'
import os, base64
print(base64.b64encode(os.urandom(32)).decode())
PY

# 设置环境变量（添加到 ~/.bashrc 或 ~/.zshrc）
export MW4AGENT_SECRET_KEY="<生成的base64密钥>"
```

**密钥要求**：
- 长度：16/24/32 字节（对应 AES-128/192/256）
- 推荐：32 字节（AES-256-GCM）
- 格式：base64 编码或原始 UTF-8 字符串（不推荐）

### 密钥未配置时的行为

- **读取**：如果文件是加密格式但密钥未配置，会抛出 `EncryptionConfigError`
- **写入**：如果密钥未配置，会回退到明文写入（并打印警告）
- **迁移**：支持 `fallback_plaintext=True` 选项，允许从明文文件平滑迁移

## 核心 API

### EncryptedFileStore

```python
from mw4agent.crypto import EncryptedFileStore, EncryptionConfigError

# 创建加密存储实例
store = EncryptedFileStore(key=your_key_bytes)

# 写入 JSON 文件（自动加密）
store.write_json("/path/to/config.json", {"key": "value"})

# 读取 JSON 文件（自动解密）
data = store.read_json("/path/to/config.json", fallback_plaintext=True)
```

### get_default_encrypted_store()

获取进程级别的默认加密存储实例（从 `MW4AGENT_SECRET_KEY` 读取密钥）：

```python
from mw4agent.crypto import get_default_encrypted_store

store = get_default_encrypted_store()
data = store.read_json("/path/to/file.json")
```

## 配置管理（ConfigManager）

### 基本用法

```python
from mw4agent.config import ConfigManager, get_default_config_manager

# 使用默认配置管理器（~/.mw4agent/config/）
config_mgr = get_default_config_manager()

# 读取配置
config = config_mgr.read_config("gateway", default={"port": 18790})
print(config["port"])

# 写入配置（自动加密）
config_mgr.write_config("gateway", {
    "port": 18790,
    "bind": "127.0.0.1",
    "session_file": "~/.mw4agent/gateway.sessions.json"
})

# 列出所有配置
configs = config_mgr.list_configs()
print(configs)  # ['gateway', 'agent', ...]

# 删除配置
config_mgr.delete_config("gateway")
```

### 自定义配置目录

```python
from mw4agent.config import ConfigManager

# 使用自定义目录
config_mgr = ConfigManager(config_dir="/custom/path/to/configs")
config_mgr.write_config("custom", {"key": "value"})
```

### 配置文件位置

- **默认目录**：`~/.mw4agent/config/`
- **文件格式**：`<name>.json`（自动添加 `.json` 扩展名）
- **存储方式**：加密存储（如果密钥已配置）或明文存储（回退模式）

## Skills 管理（SkillManager）

### 基本用法

```python
from mw4agent.skills import SkillManager, get_default_skill_manager

# 使用默认技能管理器（~/.mw4agent/skills/）
skill_mgr = get_default_skill_manager()

# 读取技能
skill = skill_mgr.read_skill("file_operations")
if skill:
    print(skill["name"], skill["description"])

# 写入技能（自动加密）
skill_mgr.write_skill("file_operations", {
    "name": "File Operations",
    "description": "Read and write files",
    "tools": ["read_file", "write_file"],
    "examples": [
        "Read the file at /path/to/file.txt",
        "Write 'Hello' to /tmp/test.txt"
    ]
})

# 列出所有技能
skills = skill_mgr.list_skills()
print(skills)  # ['file_operations', 'web_search', ...]

# 读取所有技能
all_skills = skill_mgr.read_all_skills()
for name, data in all_skills.items():
    print(f"{name}: {data['description']}")

# 删除技能
skill_mgr.delete_skill("file_operations")
```

### 自定义技能目录

```python
from mw4agent.skills import SkillManager

# 使用自定义目录
skill_mgr = SkillManager(skills_dir="/custom/path/to/skills")
skill_mgr.write_skill("custom_skill", {"name": "Custom"})
```

### 技能文件位置

- **默认目录**：`~/.mw4agent/skills/`
- **文件格式**：`<name>.json`（自动添加 `.json` 扩展名）
- **存储方式**：加密存储（如果密钥已配置）或明文存储（回退模式）

## Sessions 管理（已集成加密）

SessionManager 已经集成了加密框架：

```python
from mw4agent.agents.session.manager import SessionManager

# Session 文件会自动使用加密存储
session_mgr = SessionManager("/path/to/sessions.json")

# 读取和写入会自动加密/解密
session_mgr.get_or_create_session("session_key", "session_id")
```

## 完整示例

### 示例 1：配置 Gateway

```python
from mw4agent.config import get_default_config_manager

config_mgr = get_default_config_manager()

# 写入 Gateway 配置（自动加密）
config_mgr.write_config("gateway", {
    "port": 18790,
    "bind": "127.0.0.1",
    "session_file": "~/.mw4agent/gateway.sessions.json",
    "timeout_ms": 30000
})

# 读取配置
gateway_config = config_mgr.read_config("gateway")
print(f"Gateway running on {gateway_config['bind']}:{gateway_config['port']}")
```

### 示例 2：管理 Skills

```python
from mw4agent.skills import get_default_skill_manager

skill_mgr = get_default_skill_manager()

# 创建新技能
skill_mgr.write_skill("web_search", {
    "name": "Web Search",
    "description": "Search the web for information",
    "tools": ["web_search"],
    "examples": [
        "Search for 'Python async programming'",
        "Find information about 'FastAPI'"
    ],
    "enabled": True
})

# 读取并验证
skill = skill_mgr.read_skill("web_search")
assert skill["enabled"] == True
```

### 示例 3：迁移现有明文文件

```python
import json
from mw4agent.crypto import get_default_encrypted_store

store = get_default_encrypted_store()

# 读取明文文件
with open("/path/to/old_config.json", "r") as f:
    data = json.load(f)

# 写入加密文件（自动加密）
store.write_json("/path/to/new_config.json", data)

# 验证：读取加密文件
encrypted_data = store.read_json("/path/to/new_config.json", fallback_plaintext=False)
assert encrypted_data == data
```

## 错误处理

### EncryptionConfigError

当加密配置错误时（例如密钥未设置或格式错误），会抛出 `EncryptionConfigError`：

```python
from mw4agent.crypto import EncryptionConfigError, get_default_encrypted_store

try:
    store = get_default_encrypted_store()
except EncryptionConfigError as e:
    print(f"Encryption not configured: {e}")
    # 提示用户设置 MW4AGENT_SECRET_KEY
```

### 文件读取错误

```python
from mw4agent.config import ConfigManager

config_mgr = ConfigManager()

# 读取不存在的配置（返回默认值）
config = config_mgr.read_config("nonexistent", default={})
assert config == {}

# 读取存在的配置
config = config_mgr.read_config("gateway")
if config:
    print("Config loaded:", config)
```

## 安全建议

1. **密钥管理**：
   - 使用强随机密钥（32 字节）
   - 将密钥存储在环境变量中，不要硬编码
   - 不要将密钥提交到版本控制系统

2. **文件权限**：
   - 确保配置目录权限：`chmod 700 ~/.mw4agent`
   - 限制文件读取权限：`chmod 600 ~/.mw4agent/config/*.json`

3. **密钥轮换**：
   - 定期轮换密钥（例如每季度）
   - 轮换时先解密所有文件，再用新密钥重新加密

4. **备份**：
   - 定期备份加密文件
   - 同时备份密钥（存储在安全的密钥管理系统中）

## 与 OpenClaw 的对比

MW4Agent 的加密框架设计参考了 OpenClaw 的思路，但做了以下简化：

- **统一算法**：只使用 AES-GCM（OpenClaw 可能支持多种算法）
- **密钥来源**：仅支持环境变量（OpenClaw 可能支持密钥文件）
- **文件格式**：简化的 v1 格式（OpenClaw 可能有更复杂的版本管理）

## 后续扩展

未来可以考虑：

1. **密钥文件支持**：从 `~/.mw4agent/secret.key` 读取密钥
2. **密钥轮换工具**：提供命令行工具批量重加密文件
3. **多算法支持**：支持 XChaCha20-Poly1305 等算法
4. **版本管理**：支持加密格式版本升级

## 相关文档

- [Agent LLM 集成](agents/agent_llm.md)
- [Gateway 架构](gateway/mw4agent-gateway-agent-interaction.md)
- [Session 管理](../mw4agent/agents/session/manager.py)
