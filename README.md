# Cardputer Buddy Daemon

A macOS daemon that bridges [Claude Code](https://claude.ai/code) session activity to an [M5Stack Cardputer](https://docs.m5stack.com/en/core/Cardputer) over BLE, turning the Cardputer into a physical companion device with a Tamagotchi-style nurturing system.

macOS 守护进程，通过 BLE 把 [Claude Code](https://claude.ai/code) 的 session 活动桥接到 [M5Stack Cardputer](https://docs.m5stack.com/en/core/Cardputer)，将 Cardputer 变成一个带养成玩法的物理伴侣设备。

## How It Works / 工作原理

```
Claude Code hooks ──► Unix socket ──► Daemon ──► BLE ──► Cardputer
  (SessionStart,       hook_to_        (asyncio,      (Nordic      (MicroPython,
   Stop, etc.)         daemon.sh        bleak)         UART)       Tamagotchi UI)
```

1. Claude Code fires hook events (SessionStart, Stop, UserPromptSubmit, etc.)
2. A shell wrapper forwards the event JSON to the daemon's Unix socket
3. The daemon aggregates sessions and sends periodic heartbeats over BLE
4. The Cardputer displays coding activity and runs a Tamagotchi nurturing system

---

1. Claude Code 触发 hook 事件（SessionStart、Stop、UserPromptSubmit 等）
2. Shell 脚本把事件 JSON 转发到 daemon 的 Unix socket
3. Daemon 聚合 session 状态，通过 BLE 定期发送心跳
4. Cardputer 显示编码活动，运行养成系统

## Tamagotchi System / 养成系统

The buddy on screen responds to your coding activity:

- **Hunger & Mood** grow when Claude Code is actively running (+5/+3 every 5 minutes)
- **Task completion** gives a mood and XP boost (+20 mood, +5 XP)
- **Decay**: hunger drops by 15 every 6 hours, mood by 10 every 8 hours
- **Evolution**: XP accumulates through triangular progression — baby (lvl 0-4) → adult (lvl 5-9) → master (lvl 10+, with a crown)
- **Behavior**: low hunger slows movement, low mood causes frequent blinking, both critically low shows "Feed me!"
- All stats persist in NVS across reboots

---

屏幕上的 buddy 会对你的编码活动做出反应：

- **饥饿和心情** 在 Claude Code 活跃时增长（每 5 分钟 +5/+3）
- **任务完成** 心情和经验大幅提升（心情 +20，经验 +5）
- **衰减**：饥饿每 6 小时 -15，心情每 8 小时 -10
- **进化**：经验按三角级数累积 — 幼体（0-4 级）→ 成体（5-9 级）→ 大师（10+ 级，戴皇冠）
- **行为**：饥饿低时减速，心情低时频繁眨眼，两者都极低时显示 "Feed me!"
- 所有属性通过 NVS 跨重启持久化

## Requirements / 依赖

- macOS (LaunchAgent-based daemon)
- Python 3.10+
- [Claude Code](https://claude.ai/code)
- [M5Stack Cardputer or Cardputer-Adv](https://docs.m5stack.com/en/core/Cardputer) with the buddy bundle flashed

## Install / 安装

```bash
git clone https://github.com/yuxiaoyang2007-prog/cardputer-buddy-daemon.git
cd cardputer-buddy-daemon
scripts/install_daemon.sh
```

The installer creates `~/.cardputer-daemon/`, installs [bleak](https://github.com/hbldh/bleak) into a venv, renders a LaunchAgent plist, and asks before bootstrapping. Configure Claude Code hooks as described in the [daemon docs](README-daemon.md).

安装脚本会创建 `~/.cardputer-daemon/`，在 venv 中安装 [bleak](https://github.com/hbldh/bleak)，渲染 LaunchAgent plist，启动前会询问确认。按 [daemon 文档](README-daemon.md) 配置 Claude Code hooks。

## Device Setup / 设备端设置

The Cardputer needs the buddy bundle flashed. See the [build-with-claude](https://github.com/yuxiaoyang2007-prog/build-with-claude) fork for device-side code, or use the upstream [moremas/build-with-claude](https://github.com/moremas/build-with-claude) and apply the Tamagotchi patches from that fork.

Cardputer 需要刷入 buddy bundle。设备端代码见 [build-with-claude](https://github.com/yuxiaoyang2007-prog/build-with-claude) fork，或在上游 [moremas/build-with-claude](https://github.com/moremas/build-with-claude) 基础上应用该 fork 的养成系统补丁。

## Project Structure / 项目结构

| File | Purpose |
|------|---------|
| `daemon.py` | asyncio entrypoint, flock, logging, event consumer |
| `session_store.py` | Session upsert, counters, TTL prune, heartbeat snapshot |
| `socket_server.py` | Unix socket JSON line protocol |
| `ble_client.py` | BLE client with reconnect backoff (via bleak) |
| `hook_to_daemon.sh` | Claude Code hook wrapper |
| `bridge.py` | Standalone one-shot BLE message sender |
| `scripts/` | Install, uninstall, status scripts |
| `tests/` | Unit tests for session store, socket server, BLE client |

## Acknowledgments / 致谢

This project builds on top of the following open source projects:

本项目基于以下开源项目构建：

| Project | License | Usage |
|---------|---------|-------|
| [build-with-claude](https://github.com/moremas/build-with-claude) by Anthropic | Apache 2.0 | Device-side buddy bundle (our Tamagotchi system is built on top of it) |
| [bleak](https://github.com/hbldh/bleak) | MIT | BLE communication from macOS to ESP32 |
| [MicroPython](https://micropython.org/) | MIT | Runtime on the Cardputer (via UIFlow 2.0) |
| [M5Stack UIFlow 2.0](https://uiflow2.m5stack.com/) | MIT | Firmware and hardware abstraction layer |
| [pyserial](https://github.com/pyserial/pyserial) | BSD-3-Clause | USB serial communication for device flashing |

## License / 许可证

Apache 2.0 — see [LICENSE](LICENSE).
