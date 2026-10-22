# ✍️ AIライティングツール

Python + Streamlit + Gemini API で作った個人用のAIライティングツールです。

## 機能

| ツール | 内容 |
| --- | --- |
| 📝 ブログ記事作成 | テーマ・読者・キーワードから見出し付きの記事を執筆 |
| ✉️ メール返信作成 | 受信メールを貼り付けて返信文（件名＋本文）を作成 |
| 📋 文章要約 | 箇条書き・3行まとめなど形式を選んで要約 |
| ✏️ 文章校正・リライト | 誤字脱字チェックや表現の書き換え（修正点の説明付き） |
| 🌐 翻訳 | 多言語への自然な翻訳 |
| 📱 SNS投稿作成 | X / Instagram などに合わせた投稿文を複数パターン作成 |
| 💡 タイトル・キャッチコピー | 記事タイトル・件名・コピー案を大量に提案 |
| 🧠 アイデア出し | ブログネタや企画のブレインストーミング |
| 💬 フリープロンプト | 自由な依頼 |

共通機能: ストリーミング表示 / 追加指示での修正 / Markdown ダウンロード / 生成履歴（セッション内のみ）/ モデル・temperature の切り替え

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # .env に GEMINI_API_KEY を設定
streamlit run app.py
```

API キーは [Google AI Studio](https://aistudio.google.com/apikey) で取得できます。`.env` を作らなくても、サイドバーから入力できます。

## ファイル構成

- `app.py` — 画面（Streamlit）
- `tools.py` — 各ツールの入力項目とプロンプト定義。**ツールを追加したいときはここに `Tool` を足すだけ**
- `gemini_client.py` — Gemini API 呼び出し
