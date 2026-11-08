---
title: "剩余风险与设计取舍"
description: '五类剩余风险（含一处此前误判为不存在的出站网络策略）、六层路径防护的设计逻辑，以及为什么是 per-thread 而非 per-user 沙箱。'
topics: [governance, execution]
verified_against: v2.2.0
last_verified: 2026-11-08
---

# 剩余风险与设计取舍

前四篇讲了「有什么」。本页讲「还剩下什么」和「为什么这样设计」。

## 1. 五类剩余风险

| 风险 | 现状 | 边界 |
|------|------|------|
| **Local 模式宿主 bash** | `allow_host_bash` 默认 `false`（`config.example.yaml:1720`），可被显式打开 | 打开后路径校验是唯一屏障 |
| **容器逃逸** | Docker / K3s 依赖容器运行时安全 | 框架层无能为力 |
| **资源耗尽** | AIO 本地 Docker 默认 **2 CPU / 2G 内存 / pids 512**（`community/aio_sandbox/local_backend.py:240-242`，可用 `DEER_FLOW_SANDBOX_*` 调整）；Local 模式无 cgroup；**磁盘无配额** | 需在容器/主机层再限制 |
| **出站网络** | **部分**：AIO 本地 Docker 有受限模式；默认 `LocalSandboxProvider` 无策略（见 §2.2） | 受限模式仅 Docker 28+ |
| **Skills 注入** | 静态扫描（`skills/skillscan/orchestrator.py`）+ LLM 扫描（`skills/security_scanner.py:97`）两层 | 扫描是启发式，非形式化证明 |

## 2. 出站网络策略：一处此前被漏掉的机制

早期版本的本页写「Agent 可以通过 curl/wget 访问外网」，没有提到框架已有出站策略。
`config.example.yaml:1795-1808` 实际提供了三档：

| 模式 | 行为 |
|---|---|
| `open`（默认） | 保持现状——出站不限制 |
| `isolated` | **拒绝全部出站** |
| `allowlist` | 只允许列出的 HTTP/HTTPS 域名 |

```yaml
network:
  mode: allowlist
  allow_domains:
    - pypi.org
    - files.pythonhosted.org
  approval: prompt                  # deny | prompt
  temporary_grant_ttl: 300          # 30-3600 seconds
```

### 2.1 三个细节值得单独说

| 细节 | 含义 |
|---|---|
| `approval: prompt` | **这是本框架里少有的真实人工审批点**——被拒的域名可以从 Human Input 卡片申请放行 |
| `temporary_grant_ttl` | 放行是**有时限**的（30–3600 秒），不是永久白名单 |
| 私网地址**始终拒绝** | 原文："Private, loopback, link-local, multicast, and cloud metadata addresses are always denied" |

第三行尤其重要：**云元数据地址（169.254.169.254）始终被封**，
这是 SSRF 提权的经典路径，框架直接堵死，且不可配置。

### 2.2 适用的边界

`config.example.yaml:1798-1799` 原文：

> Restricted modes require **Docker Engine 28+** and are **not supported by Apple
> Container or provisioner mode**.

| 场景 | 受限模式可用 |
|---|---|
| 本地 Docker 沙箱（Docker 28+） | **是** |
| Apple Container | **否** |
| provisioner（K3s） | **否** |
| 默认 `LocalSandboxProvider` | **否**——无出站策略，`curl` 直连宿主网络 |

**最后一行是最需要知道的**：这套出站策略只在 **AIO 本地 Docker 后端**成立；
用默认 Local 或 K8s Provisioner 做多租户时吃不到它，网络限制需在主机/K8s 层
（NetworkPolicy）自行实现。

实现位置：`sandbox/sandbox_provider.py:118`（`sandbox_network_mode`）、
`:122`（`sandbox_network_temporary_grant_ttl`），
消费点在 `sandbox/middleware.py:347` 与 `:612`。

## 3. 为什么是六层而不是一层

单一防护（比如只做 `path.relative_to` 检查）的缺陷是：**一个 bug 全线崩溃**。
六层设计的原则是「每层都假设前面的层已经被绕过」：

| 层 | 假设什么失效了 |
|---|---|
| 1 虚拟路径 | tool 层翻译出 bug → 限制 blast radius |
| 2 工具层翻译 | 沙箱层出问题 → 独立校验 |
| 3 `allow_host_bash` | 前面全失效 → 最粗粒度的开关 |
| 4 CWD 注入 | 命令构造有 bug → 缩小默认工作目录 |
| 5 路径参数校验 | 第 4 层没生效 → 最后一层参数过滤 |
| 6 输出脱敏 | 一切正常但路径意外泄露 → 信息泄露的最后防线 |

**这套设计的现实前提**：Local 模式下没有内核级隔离，路径翻译是唯一屏障。
所以叠加层数不是过度设计，而是补偿。

各层的真实位置与局限见 [02-path-containment.md](02-path-containment.md)。

## 4. 为什么 per-thread 而非 per-user

| 取向 | 好处 | 代价 |
|---|---|---|
| **per-thread**（现状） | thread 间文件不互相污染；审计边界清晰 | N 个 thread = N 个实例 |
| per-user | 实例少，内存省 | thread A 的文件可被 thread B 覆盖/读取 |

框架选了 per-thread，代价用 LRU 缓存控制
（`local_sandbox_provider.py:33`，上限 256）。

**这个取舍的治理含义**：「同一用户的两个 thread 互不可见」
是由目录布局保证的，不是由身份保证的——两者在审计上的可信度不同。

## 5. 缺口

| 缺口 | 状态 | 边界 |
|---|---|---|
| CPU / 内存 / 磁盘配额 | **无** | Local 模式无 cgroup |
| 出站网络策略（provisioner 模式） | **无** | 受限模式明确不支持 provisioner |
| 容器逃逸防护 | **无** | 依赖运行时，框架不管 |
| Skills 扫描的形式化保证 | **无** | 静态规则 + LLM，均为启发式 |
| 高危文件操作的审批 | **无** | 只有网络域名放行有审批（§2.1） |

## 6. 与其他章节的关系

- 沙箱模式：[01-sandbox-modes.md](01-sandbox-modes.md)
- 路径防护细节：[02-path-containment.md](02-path-containment.md)
- 资源限额：[03-resource-limits.md](03-resource-limits.md)
- Skills 扫描机制：[../data/03-upload-and-scanning.md](../data/03-upload-and-scanning.md) §3
- 审批点的整体缺失：[../authorization/02-bounded-autonomy.md](../authorization/02-bounded-autonomy.md) §3
