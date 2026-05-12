---
schema_version: 1
for_review: review-plan-2.md
iteration: 2
timestamp: 2026-05-12T13:35:00Z
---

decisions:
  - id: META-SCHEMA-EXTRA-FIELDS
    type: meta
    decision: deferred
    action: review-plan-2.md frontmatter 引入了 verdict / blocker_count / suggestion_count / nit_count / first_review_blockers / testability_assessment / sessionend_assessment 等 REVIEW-SCHEMA 未定义字段；issue 用 finding / evidence / impact / required_fix / recommended_fix 替代了标准的 issue / why / fix。按 REVIEW-SCHEMA 字面规则算 malformed。CC 选择接受内容（按字段语义映射），记录此偏离；下轮 prompt 强化要求严格 schema。
    rationale: review 实质内容有价值——明确验证 iteration-1 七个 blocker 全部 fixed / mostly_fixed / rejected_correctly，新提 1 个真实 blocker + 2 个合理 suggestion。重跑 codex 让它"裁剪字段"成本高且不一定成功（codex 习惯把 review 写得"丰富"）。连续两轮 schema 偏离已超出 cc-codex 设计假设——root cause 是 cc-codex skill 与 codex CLI 自由输出风格的接口张力，应在 skill 升级时由 runner 侧后处理或 codex 提示词模板侧约束。当前不阻塞流程；iteration-3 prompt 加严要求纯 schema。
  - id: PLAN-6.0-CONFIG-SAFETY
    type: blocker
    decision: fixed
    action: 改 PLAN §6 切片 0：把 SessionEnd 触发实测的步骤重写，遵循项目 Config 变更安全规则。具体补充：(a) 先 `jq '.hooks // {}' ~/.claude/settings.json` 读当前 hooks 配置；(b) 生成临时 patch 显式 diff 给用户确认；(c) 用户确认后 apply，并 `jq .` 验证语法；(d) /exit 重启 CC；(e) 实测后**同样走 diff → 用户确认 → apply → jq . 验证**的流程拆除临时 hook；(f) 实测结论 + 双方向 diff 路径都记入 SUMMARY.md。
    rationale: 这是真实 blocker。原 PLAN 切片 0 只写"改 ~/.claude/settings.json"和"完事拆掉临时 hook"，违反项目 CLAUDE.md 的"先读 → 先 diff → 再改 → 后验"红线。前置实测本身就操作核心配置文件，必须按规则走。
  - id: PLAN-3.D-FALLBACK-ROTATE
    type: suggestion
    decision: fixed
    action: 改 PLAN §3 决策 D：hook_to_daemon.sh 写 fallback log 前先 `[ "$(stat -f%z ~/.cardputer-daemon/hook-fallback.log 2>/dev/null || echo 0)" -gt 5242880 ] && mv hook-fallback.log hook-fallback.log.1`（5MB 阈值，单文件 rename rotation，保留 1 份历史）。简单可靠，无外部依赖。
    rationale: 24/7 场景 daemon 长时间不可达 + CC 自动 loop 会持续写 fallback log。手工切日志违反 v0.1 "无人值守"语义。加 5MB cap + 1 份历史 rotation 是低成本可靠方案，比换成 Python wrapper 简单。
  - id: PLAN-4.TTL-QUEUE
    type: suggestion
    decision: fixed
    action: 改 PLAN §4 + §5.3 + §6 切片 4：TTL pruner 不再作为独立 task 直接修改 sessions，改为每分钟由独立 task 投递一个 `{"type":"prune_tick"}` 内部事件到 event_queue，由 event_consumer 统一处理（apply_event 拓展 prune_tick 分支调用 prune_inactive）。这样"单一 consumer 串行所有 session_store 修改"的不变式成立。
    rationale: review 这条 suggestion 是 judgment_call=true（说"asyncio 单线程下通常不会造成 data race"）但确实让架构不一致——claim 是"单 consumer 解决并发"，TTL 又走独立 task 自己改 sessions。一致性比"通常不会出问题"更值得，统一走 event_queue 也让单元测试更容易（构造 prune_tick 事件而不是 mock 时钟）。
