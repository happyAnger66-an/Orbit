# MW4Agent 加密框架文档

## 概述

MW4Agent 提供了一套统一的加密文件存储框架，用于保护所有敏感文件（配置、skills、sessions 等）。

## 文档索引

- [加密框架使用文档](encryption-framework.md)：完整的 API 文档和使用示例
  - 密钥管理
  - ConfigManager 使用
  - SkillManager 使用
  - SessionManager 集成
  - 错误处理和安全建议

## 快速开始

### 1. 设置加密密钥

```bash
# 生成密钥
python3 - << 'PY'
import os, base64
print(base64.b64encode(os.urandom(32)).decode())
PY

# 设置环境变量
export MW4AGENT_SECRET_KEY="<生成的base64密钥>"
```

### 2. 使用配置管理

```python
from mw4agent.config import get_default_config_manager

config_mgr = get_default_config_manager()
config_mgr.write_config("gateway", {"port": 18789})
config = config_mgr.read_config("gateway")
```

### 3. 使用技能管理

```python
from mw4agent.skills import get_default_skill_manager

skill_mgr = get_default_skill_manager()
skill_mgr.write_skill("my_skill", {"name": "My Skill"})
skill = skill_mgr.read_skill("my_skill")
```

## 已集成加密的模块

- ✅ **Sessions**：`SessionManager` 已集成加密读写
- ✅ **Config**：`ConfigManager` 提供配置文件的加密存储
- ✅ **Skills**：`SkillManager` 提供技能文件的加密存储

## 技术细节

- **算法**：AES-256-GCM（对称加密）
- **密钥来源**：环境变量 `MW4AGENT_SECRET_KEY`
- **文件格式**：自定义 v1 格式（文件头 + JSON 元数据 + base64 密文）
- **向后兼容**：支持从明文文件平滑迁移

## 相关代码

- 加密核心：`mw4agent/crypto/secure_io.py`
- 配置管理：`mw4agent/config/manager.py`
- 技能管理：`mw4agent/skills/manager.py`
- Session 管理：`mw4agent/agents/session/manager.py`
