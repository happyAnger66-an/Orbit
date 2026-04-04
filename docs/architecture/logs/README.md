# 日志实现说明

Orbit 的日志采用**异步、非阻塞**实现：主线程只将日志记录放入队列，由后台线程负责写入控制台、文件或远程日志主机，避免 I/O 阻塞业务线程，提高性能。

---

## 1. 使用方式

```python
from orbit.log import setup_logging, get_logger

# 进程启动时调用一次（CLI 入口已自动调用）
setup_logging()

logger = get_logger(__name__)
logger.info("message")
logger.debug("detail")
logger.warning("warn")
logger.error("error", exc_info=True)
```

CLI 启动时已自动执行 `setup_logging()`，业务代码只需 `get_logger(__name__)` 即可。

---

## 2. 输出目标（环境变量配置）

| 环境变量 | 说明 | 默认 |
|----------|------|------|
| `ORBIT_LOG_LEVEL` | 级别：DEBUG / INFO / WARNING / ERROR | INFO |
| `ORBIT_LOG_CONSOLE` | 是否输出到 stderr：1/0、true/false | 1（开启） |
| `ORBIT_LOG_FILE` | 日志文件路径；设置后启用按大小轮转的文件日志 | 未设置 |
| `ORBIT_LOG_FILE_MAX_BYTES` | 单文件最大字节数（轮转） | 10485760（10MB） |
| `ORBIT_LOG_FILE_BACKUP_COUNT` | 保留的备份文件个数 | 5 |
| `ORBIT_LOG_HOST` | 远程日志主机，格式 `host:port`（TCP） | 未设置 |
| `ORBIT_LOG_FORMAT` | 可选格式串 | `%(asctime)s [%(levelname)s] %(name)s: %(message)s` |

- **控制台**：`ORBIT_LOG_CONSOLE=1` 时输出到 stderr。
- **文件**：设置 `ORBIT_LOG_FILE=/path/to/orbit.log` 即写入该文件，并按大小轮转。
- **日志主机**：设置 `ORBIT_LOG_HOST=127.0.0.1:9020` 时，通过 TCP 将序列化后的 `LogRecord` 发送到该地址（需对端为可接收 Python `logging.handlers.SocketHandler` 格式的接收端或兼容服务）。

---

## 3. 实现要点

- **QueueHandler + QueueListener**：根 logger 使用 `QueueHandler` 将记录放入 `queue.Queue`；`QueueListener` 在单独线程中从队列取记录并分发给各 handler（StreamHandler、RotatingFileHandler、SocketHandler 等），主线程仅做 `queue.put()`，不直接写 I/O。
- **代码位置**：`orbit/log/__init__.py`，提供 `setup_logging()`、`get_logger()`、`stop_logging()`。
- **初始化时机**：CLI 的 `main()` 在解析参数前调用 `setup_logging()`，之后所有通过 `get_logger()` 得到的 logger 都会走队列与后台线程输出。

---

## 4. 示例

```bash
# 仅控制台，INFO 级别（默认）
orbit gateway run

# 同时写文件
export ORBIT_LOG_FILE=/var/log/orbit.log
orbit gateway run

# 同时发往日志主机
export ORBIT_LOG_HOST=logserver.example.com:9020
orbit channels console run

# 调试时提高级别
ORBIT_LOG_LEVEL=DEBUG orbit channels console run
```
