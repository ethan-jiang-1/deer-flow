---
title: "Sandbox — 统一沙箱系统"
description: "统一执行抽象 + 七种 provider：执行租约、受控出口、隔离记录，以及 2.2.0 的可重试关闭、124 超时与文件契约。"
type: index
topics: [sandbox, isolation, execution]
---

# Sandbox — 统一沙箱系统

> **定位**：回答「Agent 的代码到底在哪跑、凭什么隔离、谁负责清理」。核心是 `Sandbox` / `SandboxProvider` 抽象、七种 provider 实现，以及租约、受控出口与 2.2.0 的硬化增量。给写 provider、调隔离策略或排查沙箱泄漏的人。
> **边界**：不覆盖 AIO 容器的 Docker/K3s 运维细节（见 [community-tools/04-aio-sandbox.md](../community-tools/04-aio-sandbox.md)），不覆盖工具层的参数与返回语义（见 [builtin-tools/B-sandbox-filesystem.md](../builtin-tools/B-sandbox-filesystem.md)），也不覆盖部署侧端口绑定与网络拓扑（见 [enterprise-operations/deployment](../../enterprise-operations/deployment/README.md)）。

## 阅读路径

1. **先看**：[abstract-interface-and-seven-impls.md](abstract-interface-and-seven-impls.md) — 「抽象接口 / 七种实现」两节：acquire / get / release 与 warm-pool 生命周期。
2. **深入**：同篇「网络 Egress 控制」「可重试的 shutdown」「bash 硬超时与 `Exit Code: 124`」三节 — 谁放行出口、失败怎么重试、超时怎么判定。

## 本篇目

| 文件 | 主题 | 深度 |
|---|---|---|
| [abstract-interface-and-seven-impls.md](abstract-interface-and-seven-impls.md) | 接口契约、七实现、ownership 与执行租约、受控出口、授权门控、2.2.0 硬化 | 深入 |

## 速览

- **抽象接口**：`Sandbox` + `SandboxProvider`（acquire / get / release）；per-call `env` 注入密钥；`execute_command_in_scope` / `release_command_scope` 为增量钩子；list_dir / glob / grep 失败返回 `OSError` / `FileNotFoundError`，绝不伪装成空结果（#5264/#5380）。
- **七种实现**：Local / AIO(Docker) / Provisioner(K3s) / BoxLite / E2B / Tenki / OpenSandbox，共享 `WarmPoolLifecycleMixin`；跨实例 ownership 用 `sandbox.ownership.type: memory|redis` 的 `own:` / `del:` 双状态租约回答「谁 reap」，区分 `LAPSED` 与 `LOST`，并给 orphan 对账留 grace（#4206）。
- **执行与门控**：进程内 `SandboxLeaseManager` 按 holder 计数、最后持有者才 release；`sandbox:execute` 授权在 acquire **与复用前**都检查（#5006 复用重查），deny 返回友好 ToolMessage。受控出口 `sandbox.network` 为 `open|isolated|allowlist` + `prompt|deny` 审批，每沙箱一个 ICC-disabled proxy sidecar（#5152）。
- **共享组件**：`identity.py` 的 `derive_sandbox_scope_token`（keyword-only、SHA-256/16-hex 兼容契约）、`acquire_serialization.py` 的有界 per-key 锁表与专用 executor、`path_patterns.py` 的段边界匹配（RFC #4741 / #5089）。
- **2.2.0 增量**：五个 provider「要么全清干净并关闭，要么复位成未关闭并抛出让调用方重试」；`quarantine.py`（160 行）把残留旧代容器写成带 `sha256(...)[:16]` 键的本地标记；`prewarm.py`（232 行）只对 AIO 且 `sandbox.prewarm: true` 生效，`should_prewarm_sandbox` 只认代码围栏 / 路径 / 命令行 / traceback 四类信号，真实工具获取永不排在它后面；bash 超时统一 `Exit Code: 124`；`read_file_contract.py` / `download.py` 统一文件与下载契约（100 MiB / 20 MiB，调用方只能收紧）。

## 宪章与约定

- 本目录无独立宪章；研究纪律沿用 [根 README](../../README.md)（不修改源码、`main` 只镜像上游、笔记只落在 `ethan`）。
- 正文文件名沿用历史（"seven-impls"），内容已同步 v2.2.0；安全机制的 issue/RFC 编号保留在正文，README 只留结论。

## 相关目录

- [community-tools/](../community-tools/README.md) — AIO / BoxLite / E2B / Tenki 的 provider 侧实现。
- [builtin-tools/](../builtin-tools/README.md) — 沙箱七工具如何把路径与权限交给 sandbox。
- [subagent/](../subagent/README.md) — 子 agent 的沙箱租约与验收清单执行。
- [enterprise-operations/security/](../../enterprise-operations/security/README.md) — 隔离、Guardrail 与信任链的企业视角。
