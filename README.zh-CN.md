# Agent Context Lens

[English](README.md) | **简体中文** | [日本語](README.ja.md)

> 面向社区的非官方翻译：本页面可能落后于英文 README。若内容存在冲突，以英文 README 为准。
<!-- i18n-light-meta
{
  "schema_version": 2,
  "contract_id": "I18N-001-LIGHT",
  "locale": "zh-CN",
  "canonical_file": "README.md",
  "baseline_commit": "e6498fbf7c1b89d368aea7fc42120357ef4bc27a",
  "product_version": "0.2.0",
  "human_evidence_required": false,
  "english_patch_proposal_sha256": "e8dabc6dfa0e9f803b035324bdba416095a7583ced36fb37023a0b0d7d9faa57",
  "source_manifest_sha256": "c9d8adbb26beec129c922aca73204fc283f7be231ca5f3c294fb3b05d733574a",
  "visible_golden_sha256": "801b13f40b640a944f7cf4d7e95afe43374c0b1c4ba30dc1e7ca16468147f2bb",
  "source_blocks": {
    "intro": "372f069bc415ae9c46c1d074e7dbea1c3fc3e2e0a5cd9c9f73bb4006559421f9",
    "quick-start": "9539b9f39d33414b749ae0553a619d370aa7be7412da2ec7ab02e1276d1ee50f",
    "capabilities": "199e8527036fe57ad3826e9a668c8ac73e469802e6429c886c9c5c941160aba7",
    "limitations": "8378249895026dbd25a24b782fd69b5e2b74866f167c5534f80042665d2497d8",
    "privacy-safety": "82f51e037cec3b93e20447adc186fa92e1b461da3e0bd0559965e00fff0feb82",
    "feedback": "a12d0a498cb68d2583ec0a19cbe926d8629f7221e27b1df8f8ceafe94f30d979"
  }
}
-->

适用产品版本：`0.2.0`。完整产品合同请参阅英文 README。

## 这是什么

`Agent Context Lens` 在本地确定性扫描仓库中声明的 `AGENTS.md` 等代理上下文，并提供有边界的 `Codex` 项目指令解释。

[英文 README](README.md) 是唯一的规范产品合同；本页仅提供 v0.2 的简短介绍。

## 快速开始

安装仓库版本：

<!-- i18n-command:start:QS-01 -->
```bash
python -m pip install "git+https://github.com/ciceroyang/agent-context-lens.git"
```
<!-- i18n-command:end:QS-01 -->

扫描仓库：

<!-- i18n-command:start:QS-02 -->
```bash
agent-context-lens /path/to/repository
```
<!-- i18n-command:end:QS-02 -->

解释某个工作目录的 Codex 项目指令：

<!-- i18n-command:start:QS-03 -->
```bash
agent-context-lens /path/to/repository \
  --explain --agent codex \
  --cwd /path/to/repository/services/payments \
  --project-root /path/to/repository
```
<!-- i18n-command:end:QS-03 -->

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
