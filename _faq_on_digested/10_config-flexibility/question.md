---
title: "DeerFlow 配置灵活性：config.yaml 只能固定一个文件吗？"
question: "DeerFlow 的配置是写死在 config.yaml 上的吗？能不能用不同的 .yaml 文件启动？有没有多文件组合、环境变量覆盖、命令行切换的手段？灵活性到底在哪里？"
topics: [configuration, config-yaml, flexibility, env-vars]
---

# DeerFlow 配置灵活性：config.yaml 只能固定一个文件吗？

DeerFlow 的配置看起来是"一个 `config.yaml` 吃遍天"——但这个印象不完全对。实际上有三层灵活性机制，只是有些你可能没发现。
