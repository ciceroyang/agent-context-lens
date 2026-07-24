# Agent Context Lens

[English](README.md) | **简体中文** | [日本語](README.ja.md)

> 面向社区的非官方翻译：本页面可能落后于英文 README。若内容存在冲突，以英文 README 为准。

适用产品版本：`0.2.0`。完整产品合同请参阅英文 README。

## 这是什么

`Agent Context Lens` 在本地确定性扫描仓库中声明的 `AGENTS.md` 等代理上下文，并提供有边界的 `Codex` 项目指令解释。

[英文 README](README.md) 是唯一的规范产品合同；本页仅提供 v0.2 的简短介绍。

## 快速开始

安装仓库版本：

```bash
python -m pip install "git+https://github.com/ciceroyang/agent-context-lens.git"
```

扫描仓库：

```bash
agent-context-lens /path/to/repository
```

解释某个工作目录的 Codex 项目指令：

```bash
agent-context-lens /path/to/repository \
  --explain --agent codex \
  --cwd /path/to/repository/services/payments \
  --project-root /path/to/repository
```

[查看完整英文快速开始](README.md#acl-i18n-quick-start)。

## 核心能力

扫描模式在本地生成确定性结果，用于查看已识别的代理上下文表面。

Codex 解释模式将证据分为 `official_contract`、`versioned_observation` 和 `unknown`。

这些类别不保证复现 Codex 的完整提示词。

[查看完整英文能力说明](README.md#acl-i18n-capabilities)。

## 核心限制

声明的配置不等于未来某次 Codex 调用的实际有效配置；无法验证的版本、平台、编码和文件系统行为会保持为 `unknown` 或不支持。

Agent Context Lens 不解析 `.codex/config.toml`；相关有效值未声明时会显示 `toml_config_not_parsed`。

[查看完整英文限制](README.md#acl-i18n-limitations)。

## 隐私与安全

工具在本地确定性运行，不调用模型，也不发起网络请求。

默认情况下不会打开、检查、哈希或读取 `CODEX_HOME/AGENTS.override.md` 和 `CODEX_HOME/AGENTS.md`，并报告 `user_scope_not_requested`；只有显式使用 `--include-user` 才会包含用户级指令。

在已接受的 macOS ARM64 证据范围内，安全模式会拒绝指令文件、路径目录和 `CODEX_HOME` 符号链接；其他平台的行为保持未知，因此结果不能被描述为与 Codex 完全一致或具有通用跨平台竞态安全性。

报告包含元数据和哈希，不包含指令正文。

[查看完整英文隐私与安全说明](README.md#acl-i18n-privacy-safety)。

## 反馈与完整英文文档

[查看完整英文 README](README.md)；[查看完整英文反馈说明](README.md#acl-i18n-feedback)。

[参与讨论](https://github.com/ciceroyang/agent-context-lens/discussions/1)，或通过[缺失上下文路径表单](https://github.com/ciceroyang/agent-context-lens/issues/new?template=missing_context_path.yml)提交最小复现。

安全漏洞请按照 [`SECURITY.md`](SECURITY.md) 报告。

提交反馈前，请移除密钥、私有路径和专有指令。
