# Agent Context Lens

[English](README.md) | [简体中文](README.zh-CN.md) | **日本語**

> コミュニティ向けの非公式翻訳：このページは英語版 README より更新が遅れる場合があります。内容に相違がある場合は、英語版 README を正とします。

対象製品バージョン：`0.2.0`。完全な製品契約は英語版 README を参照してください。

## Agent Context Lens とは

`Agent Context Lens` は、リポジトリで宣言された `AGENTS.md` などのエージェントコンテキストをローカルかつ決定論的にスキャンし、範囲を限定した `Codex` プロジェクト指示の説明を提供します。

[英語版 README](README.md) だけが正規の製品契約です。このページは v0.2 の短い案内のみを提供します。

## クイックスタート

リポジトリ版をインストールします。

```bash
python -m pip install "git+https://github.com/ciceroyang/agent-context-lens.git"
```

リポジトリをスキャンします。

```bash
agent-context-lens /path/to/repository
```

作業ディレクトリの Codex プロジェクト指示を説明します。

```bash
agent-context-lens /path/to/repository \
  --explain --agent codex \
  --cwd /path/to/repository/services/payments \
  --project-root /path/to/repository
```

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
