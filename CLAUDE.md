# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

個人用のAIライティングツール（ブログ記事・メール返信・要約・校正・翻訳・SNS投稿など）。Python + Streamlit + Gemini API（`google-genai` SDK）で構成。データベース・認証は意図的に持たない（履歴は `st.session_state` のみで、セッション終了で消える）。UI・プロンプト・ドキュメントは日本語。

## コマンド

```bash
# 依存関係（.venv は作成済み）
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 起動（http://localhost:8501）
.venv/bin/streamlit run app.py
.venv/bin/streamlit run app.py --server.headless true   # ブラウザを開かずに起動
```

テストスイートや linter は未導入。動作確認は Streamlit の `AppTest` でヘッドレスに行える：

```bash
.venv/bin/python -c "
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('app.py').run(timeout=30)
at.sidebar.radio[0].set_value('文章要約').run()   # ツール切り替え
print(at.exception)
"
```

APIキーは `.env` の `GEMINI_API_KEY`（`.env.example` 参照）またはサイドバー入力。`.env` の値が `your-api-key-here`（プレースホルダ）の場合は未設定扱いとなり、サイドバーに入力欄が表示される。

## アーキテクチャ

3ファイル構成で、ツールは**データ駆動**で定義されている：

- `tools.py` — 各ツールを `Tool`（名前・アイコン・`system_instruction`・`fields`・`build_prompt`・既定 `temperature`）として `TOOLS` リストに登録。`Field.kind`（`text` / `textarea` / `select` / `slider`）で入力UIの種類を指定し、`build_prompt` は `{field.key: 入力値}` の dict を受け取ってプロンプト文字列を返す。**新しいツールの追加は `TOOLS` に `Tool(...)` を1つ足すだけで、`app.py` の変更は不要。**
- `app.py` — `TOOLS` を元に、サイドバー（ツール選択・APIキー・モデル・temperature・履歴）と入力フォームを汎用的に描画。ウィジェットの key は `"{tool.name}:{field.key}"` の形式で、ツールごとに入力値を分けて保持する。`required=True` の項目は生成前に未入力チェックされる。
- `gemini_client.py` — `stream_generate()` が `generate_content_stream` をラップしてテキストチャンクを yield し、`app.py` 側で `st.write_stream` によりストリーミング表示する。モデル一覧は `list_models()` でAPIキーから動的に取得し（1時間キャッシュ）、取得失敗時は `FALLBACK_MODELS`。既定モデルは `DEFAULT_MODEL`（`gemini-2.5-flash` は新規ユーザーには404になるため使わない）。

生成フロー：生成結果は `st.session_state.results[tool.name]`（`text` と送信した `prompt`）と `st.session_state.history` に保存したあと `st.rerun()` し、再描画時に保存済みの結果を表示する。「修正を依頼する」は、元のプロンプト・前回の出力・修正指示を1つのプロンプトにまとめて再送信する方式（マルチターンのチャット履歴は使っていない）。

プロンプトの共通ルール：`BASE_SYSTEM`（Markdownで成果物のみを出力）を各ツールの `system_instruction` に連結し、任意の「追加の要望」欄は共通の `EXTRA_FIELD` と `_extra()` で末尾に付け足す。
