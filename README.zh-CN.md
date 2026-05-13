# Cardputer Buddy

[English](README.md)

给 [Claude Code](https://claude.ai/code) 做的物理伴侣设备。一台 M5Stack Cardputer 放在键盘旁边，实时响应你的编码活动——屏幕上住着一只虚拟宠物，你写代码它就吃饱，你停下来它就饿。

## 和官方 Buddy 有什么区别

官方 Claude Buddy 需要 Claude Desktop 桌面应用才能连接。这个项目只需要 **Claude Code CLI**，不依赖桌面应用。守护进程直接接入 Claude Code 的 hook 事件系统，自己完成 BLE 桥接。

## 它做什么

Cardputer 屏幕上有一个小生物。Claude Code 在跑的时候，它会被喂食；你完成一个任务，它会变得兴奋；长时间不写代码，它就饿了。

- **饥饿和心情**：Claude Code 活跃时每 5 分钟饥饿 +5、心情 +3
- **任务完成**：心情 +20，经验 +5
- **自然衰减**：饥饿每 6 小时 -15，心情每 8 小时 -10
- **进化**：幼体（0-4 级）→ 成体（5-9 级，6 条腿）→ 大师（10 级以上，戴皇冠）
- **行为反馈**：饥饿低了走得慢，心情低了一直眨眼，两个都很低就停下来喊 "Feed me!"
- 所有属性存在 ESP32 的 NVS 里，重启不丢

## 架构

```
Claude Code hooks ──► Unix socket ──► 守护进程 ──► BLE ──► Cardputer
```

Mac 端的守护进程接收 Claude Code 的 hook 事件（SessionStart、Stop 等），汇总 session 状态，通过 BLE 的 Nordic UART 协议把心跳推给 Cardputer。

## 需要什么

- macOS
- Python 3.10+
- [Claude Code](https://claude.ai/code)
- [M5Stack Cardputer 或 Cardputer-Adv](https://docs.m5stack.com/en/core/Cardputer)

## 安装

### 1. 刷 Cardputer

```bash
# 先改 WiFi 配置
nano build-with-claude/buddy/device/wifi_event.py

# 刷固件和推应用（需要 Claude Code）
# 在 Claude Code 里执行：m5-onboard go
```

### 2. 装守护进程

```bash
scripts/install_daemon.sh
```

脚本会在 `~/.cardputer-daemon/` 建 venv，装 [bleak](https://github.com/hbldh/bleak)，配好 LaunchAgent。

### 3. 配 Claude Code hooks

在 `~/.claude/settings.json` 里加（路径换成你的）：

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "bash '/你的路径/cardputer/hook_to_daemon.sh'" }] }],
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "bash '/你的路径/cardputer/hook_to_daemon.sh'" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "bash '/你的路径/cardputer/hook_to_daemon.sh'" }] }],
    "SubagentStop": [{ "hooks": [{ "type": "command", "command": "bash '/你的路径/cardputer/hook_to_daemon.sh'" }] }],
    "SessionEnd": [{ "hooks": [{ "type": "command", "command": "bash '/你的路径/cardputer/hook_to_daemon.sh'" }] }]
  }
}
```

改完重启 Claude Code。

## 项目结构

```
├── daemon.py              # Mac 守护进程入口（asyncio）
├── session_store.py        # Session 聚合，心跳生成
├── socket_server.py        # Unix socket 服务端，接收 hook 事件
├── ble_client.py           # BLE 客户端（bleak），断线自动重连
├── hook_to_daemon.sh       # Claude Code hook 的 shell 包装
├── scripts/                # 安装、卸载、状态查询脚本
├── tests/                  # 单元测试
└── build-with-claude/      # 设备端代码（M5Stack Cardputer）
    └── buddy/device/
        ├── main.py             # MicroPython 入口
        ├── buddy_state.py      # 养成属性 + NVS 持久化
        ├── buddy_protocol.py   # BLE 命令处理
        ├── buddy_ble.py        # Nordic UART BLE 外设
        ├── buddy_ui_cp.py      # 屏幕渲染
        ├── buddy_sprites.py    # 进化阶段的 sprite
        └── wifi_event.py       # WiFi 自动连接（在这里改你的密码）
```

## 调试

- 守护进程日志：`~/.cardputer-daemon/daemon.log`
- 临时静音 BLE：`touch ~/.cardputer-mute`
- 查看状态：`scripts/cardputer-daemon-status.sh`

## 致谢

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [build-with-claude](https://github.com/moremas/build-with-claude)（Anthropic） | Apache 2.0 | 原版 Cardputer buddy 代码包，养成系统在此基础上开发 |
| [bleak](https://github.com/hbldh/bleak) | MIT | macOS 到 ESP32 的 BLE 通信 |
| [MicroPython](https://micropython.org/) | MIT | 设备端运行时（通过 UIFlow 2.0） |
| [M5Stack UIFlow 2.0](https://uiflow2.m5stack.com/) | MIT | 固件和硬件抽象层 |
| [pyserial](https://github.com/pyserial/pyserial) | BSD-3-Clause | 刷机用的 USB 串口通信 |

## 许可证

Apache 2.0 — 见 [LICENSE](LICENSE)。
