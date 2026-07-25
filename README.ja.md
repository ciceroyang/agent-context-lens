# Agent Context Lens

[English](README.md) | [简体中文](README.zh-CN.md) | **日本語**

> コミュニティ向けの非公式翻訳：このページは英語版 README より更新が遅れる場合があります。内容に相違がある場合は、英語版 README を正とします。
<!-- i18n-light-meta
{
  "schema_version": 2,
  "contract_id": "I18N-001-LIGHT",
  "locale": "ja",
  "canonical_file": "README.md",
  "baseline_commit": "e6498fbf7c1b89d368aea7fc42120357ef4bc27a",
  "product_version": "0.2.0",
  "human_evidence_required": false,
  "english_patch_proposal_sha256": "e8dabc6dfa0e9f803b035324bdba416095a7583ced36fb37023a0b0d7d9faa57",
  "source_manifest_sha256": "c9d8adbb26beec129c922aca73204fc283f7be231ca5f3c294fb3b05d733574a",
  "visible_golden_sha256": "ea1048210c7da8b83696c86d62d3b163888191d2327a3ad0a6b4fb68fbb0cda1",
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

対象製品バージョン：`0.2.0`。完全な製品契約は英語版 README を参照してください。

## Agent Context Lens とは

`Agent Context Lens` は、リポジトリで宣言された `AGENTS.md` などのエージェントコンテキストをローカルかつ決定論的にスキャンし、範囲を限定した `Codex` プロジェクト指示の説明を提供します。

[英語版 README](README.md) だけが正規の製品契約です。このページは v0.2 の短い案内のみを提供します。

## クイックスタート

リポジトリ版をインストールします。

<!-- i18n-command:start:QS-01 -->
```bash
python -m pip install "git+https://github.com/ciceroyang/agent-context-lens.git"
```
<!-- i18n-command:end:QS-01 -->

リポジトリをスキャンします。

<!-- i18n-command:start:QS-02 -->
```bash
agent-context-lens /path/to/repository
```
<!-- i18n-command:end:QS-02 -->

作業ディレクトリの Codex プロジェクト指示を説明します。

<!-- i18n-command:start:QS-03 -->
```bash
agent-context-lens /path/to/repository \
  --explain --agent codex \
  --cwd /path/to/repository/services/payments \
  --project-root /path/to/repository
```
<!-- i18n-command:end:QS-03 -->

[英語版の完全なクイックスタート](README.md#acl-i18n-quick-start)を参照してください。

## 主な機能

スキャンモードは、認識されたエージェントコンテキストの範囲を確認するための決定論的な結果をローカルで生成します。

Codex 説明モードは、証拠を `official_contract`、`versioned_observation`、`unknown` に区分します。

これらの区分は Codex の完全なプロンプトの再現を保証しません。

[英語版の完全な機能説明](README.md#acl-i18n-capabilities)を参照してください。

## 主な制約

宣言された設定は、将来の Codex 実行で実際に有効になる設定と同一ではありません。検証できないバージョン、プラットフォーム、文字コード、ファイルシステムの挙動は `unknown` または未サポートのままです。

Agent Context Lens は `.codex/config.toml` を解析しません。関連する有効値が宣言されていない場合は `toml_config_not_parsed` を表示します。

[英語版の完全な制約](README.md#acl-i18n-limitations)を参照してください。

## プライバシーと安全性

本ツールはローカルかつ決定論的に動作し、モデルを呼び出さず、ネットワーク要求も行いません。

デフォルトでは `CODEX_HOME/AGENTS.override.md` と `CODEX_HOME/AGENTS.md` を開かず、検査、ハッシュ化、内容の読み取りも行いません。また `user_scope_not_requested` として報告します。ユーザー範囲の指示を含めるのは `--include-user` を明示した場合だけです。

受け入れ済みの macOS ARM64 証拠の範囲では、セーフモードは指示ファイル、パス上のディレクトリ、`CODEX_HOME` のシンボリックリンクを拒否します。他のプラットフォームの挙動は不明なため、結果を Codex と完全に同一、またはプラットフォームを問わず競合状態に対して安全なものとは表現できません。

レポートにはメタデータとハッシュが含まれ、指示本文は含まれません。

[英語版の完全なプライバシーと安全性の説明](README.md#acl-i18n-privacy-safety)を参照してください。

## フィードバックと英語版の完全なドキュメント

[英語版 README の全文](README.md)と[英語版の完全なフィードバック説明](README.md#acl-i18n-feedback)を参照してください。

[ディスカッションに参加](https://github.com/ciceroyang/agent-context-lens/discussions/1)するか、[不足しているコンテキストパスのフォーム](https://github.com/ciceroyang/agent-context-lens/issues/new?template=missing_context_path.yml)から最小限の再現例を送信してください。

セキュリティ上の脆弱性は [`SECURITY.md`](SECURITY.md) の手順に従って報告してください。

フィードバックを共有する前に、シークレット、非公開パス、プロプライエタリな指示を削除してください。
