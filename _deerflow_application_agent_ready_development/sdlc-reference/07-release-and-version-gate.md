# 发版与版本门

## 什么时候读这里

合并之后怎样上线：DeerFlow 主仓的 tag 驱动发版、版本五源一致门禁、nightly 的例外位置。应用仓直接相关的部分是**版本门的形态**——它是主仓全部 SDLC 里最强的机器门禁。

## 主仓机制

**tag 驱动，无 bump 脚本（成文标准）**。发版流程是：维护者改版本源、更新 changelog、commit、打 `v*` tag、推送。没有单独的脚本去 bump 版本——发布 workflow 由 tag 推送触发（[RELEASING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/RELEASING.md)）。

**版本五源一致（机器门禁，发布链的硬闸）**。一个发布版本必须**完全一致**地出现在：backend `pyproject.toml`、frontend `package.json`、Helm `Chart.yaml` 的 `version` 与 `appVersion`，加上 git tag 本身——共五源。container 与 chart 的发布 job 显式依赖版本校验：

> Gate the release: every version source must match the v* tag. A forgotten bump in Chart.yaml, pyproject.toml, or package.json fails here and skips all image builds.
>
> — [container.yaml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/container.yaml)

校验逻辑在 [verify-versions.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/verify-versions.yml)，可本地等价运行（`scripts/verify_versions.sh`），帮助脚本 `bump_version.sh` 一次改齐四源。

**nightly 刻意不走版本门（成文标准）**。nightly 构建从 `main` 定时发布三镜像加 chart，**不**过版本校验（没有 `v*` tag）、**不**碰 `latest` 标签（`latest` 钉在最后一个正式 release 上）。nightly 的 chart 版本带日期与 short SHA 保证唯一。

**边界（门禁的不对称）**：发布门强于日常 PR 门——普通 PR 的 CI 并不做完整生产部署/启动/回滚验收；个别 spec 把 real-path 现场验收标为 "Required before claiming feature complete"，但那是文档要求与人工步骤，不是普遍 CI 门（见 [spec 与实现计划](./02-spec-and-plan.md)）。

## 为什么值得抄

版本门回答的问题在应用仓同样存在：**"我发布的到底是什么版本？"** 主仓的答案是把版本一致性做成发布链的第一道 job——不一致就什么都不发布，而不是发布出去再发现。配合 helper 脚本（本地先跑、CI 再验），漂移在 tag 之前就会被抓到。

## 应用仓适用边界

**可移用**：tag 驱动 + 版本门 + "本地等价命令"。应用仓的"五源"清单不同——典型是：包版本文件、changelog、（若有）容器镜像 tag、git tag——但**多源一致 + 发布链首个 job 校验 + 本地可等价运行**这个三件套结构原样适用。**需要自定**：你是否需要 nightly（取决于下游是否消费不稳定版）；若要 nightly，学主仓"不碰 latest、版本带不可变后缀"的克制。**应用仓建议**：extension 包仓最低配置是两源（`pyproject.toml` 版本 + git tag）一命令（发版前本地校验脚本），成本极低。

## 证据入口

- [RELEASING.md](https://github.com/bytedance/deer-flow/blob/v2.1.0/RELEASING.md)（Version sources / Release procedure / Nightly builds）
- [verify-versions.yml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/verify-versions.yml) 与 [container.yaml](https://github.com/bytedance/deer-flow/blob/v2.1.0/.github/workflows/container.yaml)（`needs: verify-versions` 依赖链）
