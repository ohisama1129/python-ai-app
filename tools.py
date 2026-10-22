"""各ライティングツールの定義。

ツールを追加したいときは、Tool を作って TOOLS に足すだけでOK。
- fields: 画面に表示する入力項目
- build_prompt: 入力値の dict を受け取り、Gemini に送るプロンプトを返す
"""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"  # text / textarea / select / slider
    placeholder: str = ""
    options: list[str] = field(default_factory=list)
    default: int | str | None = None
    min_value: int = 0
    max_value: int = 100
    step: int = 1
    required: bool = False
    height: int = 200


@dataclass
class Tool:
    name: str
    icon: str
    description: str
    system_instruction: str
    fields: list[Field]
    build_prompt: Callable[[dict], str]
    temperature: float = 0.7


BASE_SYSTEM = "あなたはプロの日本語ライターです。出力は Markdown 形式で、前置きや後書きの説明は書かず、成果物のみを出力してください。"

TONES = ["丁寧", "カジュアル", "フォーマル", "フレンドリー", "専門的"]


def _extra(v: dict) -> str:
    return f"\n\n# 追加の要望\n{v['extra']}" if v.get("extra") else ""


EXTRA_FIELD = Field("extra", "追加の要望（任意）", "textarea", "例: 具体例を多めに", height=80)


# ---------- 各ツールのプロンプト ----------

BLOG_SYSTEM = BASE_SYSTEM + """
あなたはSEOに精通したプロのWebライターです。検索ユーザーの悩みを解決し、検索上位を狙える記事を書きます。

# SEOライティングの方針
- 検索意図を最優先する：そのキーワードで検索する人が本当に知りたいことに、記事の前半で答える
- メインキーワードは、タイトル（できるだけ前半）、メタディスクリプション、導入文、一部の見出し（##）に自然に含める
- 関連キーワードや言い換え表現も文脈に合わせて使う。同じ語の不自然な詰め込みはしない
- 見出しは ## と ### で論理的に階層化し、見出しだけ読んでも内容が分かるようにする
- 1段落は2〜4文程度。結論を先に書き、箇条書きや表も使って読みやすくする
- 具体例・手順・注意点・比較など、ほかの記事にない実用的な情報を盛り込む（E-E-A-T を意識）
- 統計データ・価格・日付などの事実は創作しない。確認が必要な情報は【要確認】と明記する"""


def blog_prompt(v: dict) -> str:
    return f"""以下の条件で、SEOを意識したブログ記事を執筆してください。

# テーマ
{v['topic']}

# メインキーワード
{v['main_keyword'] or 'テーマから最適なものを1つ選ぶ'}

# 関連キーワード
{v['keywords'] or 'メインキーワードと一緒に検索されやすい語を自分で選ぶ'}

# 検索意図
{v['intent']}

# 想定読者
{v['audience'] or '上記キーワードで検索する人'}

# 条件
- 文体: {v['tone']}
- 本文の文字数: 約{v['length']}文字

# 出力形式（この順番で出力）
1. タイトル（# 見出し）：32文字前後。メインキーワードを前半に入れ、クリックしたくなる表現にする
2. メタディスクリプション：「> **メタディスクリプション**: 」に続けて120文字前後で、記事の要約と読むメリットを書く
3. 導入文：読者の悩みへの共感と、この記事で分かることを簡潔に示す
4. 本文：## と ### の見出しで構成する
5. 「## よくある質問」：読者が抱きそうな質問を3つ、「### Q. 〜」と回答の形式で書く
6. 「## まとめ」：要点を箇条書きで振り返り、読者が次に取る行動を促す{_extra(v)}"""


def email_prompt(v: dict) -> str:
    return f"""以下のメールに対する返信文を作成してください。

# 受信したメール
{v['received']}

# 返信で伝えたいこと
{v['intent'] or '受信内容に対して適切に返答する'}

# 条件
- 相手との関係: {v['relation']}
- 文体: {v['tone']}
- 件名（「件名: 」で始まる1行）と本文を出力する
- 自分の名前などの不明な情報は【 】で示す{_extra(v)}"""


def summary_prompt(v: dict) -> str:
    return f"""以下の文章を要約してください。

# 要約形式
{v['style']}

# 長さの目安
{v['length']}

# 文章
{v['text']}{_extra(v)}"""


def proofread_prompt(v: dict) -> str:
    return f"""以下の文章を「{v['mode']}」してください。

# 文章
{v['text']}

# 出力形式
1. 「## 修正後の文章」として完成版を出力
2. 「## 主な修正点」として、変更した箇所と理由を箇条書きで簡潔に説明{_extra(v)}"""


def translate_prompt(v: dict) -> str:
    return f"""以下の文章を{v['target']}に翻訳してください。

# 翻訳スタイル
{v['style']}

# 文章
{v['text']}

訳文のみを出力し、必要な場合のみ最後に「訳注」を簡潔に付けてください。{_extra(v)}"""


def sns_prompt(v: dict) -> str:
    return f"""以下の内容で {v['platform']} 向けの投稿文を{v['count']}パターン作成してください。

# 投稿内容
{v['content']}

# 条件
- 文体: {v['tone']}
- プラットフォームの文字数制限や文化に合わせる
- 適切なハッシュタグを付ける
- 各パターンは「## パターン1」のように見出しで区切る{_extra(v)}"""


def title_prompt(v: dict) -> str:
    return f"""以下の内容に対して「{v['kind']}」の案を{v['count']}個提案してください。

# 内容
{v['content']}

# 出力形式
番号付きリストで出力し、それぞれに狙い・ポイントを一言添えてください。{_extra(v)}"""


def idea_prompt(v: dict) -> str:
    return f"""以下のテーマについて、アイデアを{v['count']}個ブレインストーミングしてください。

# テーマ
{v['theme']}

# 目的・用途
{v['purpose'] or '特になし'}

# 出力形式
各アイデアを「### 見出し」と2〜3行の説明で出力してください。ありきたりなものだけでなく、意外性のある案も混ぜてください。{_extra(v)}"""


def free_prompt(v: dict) -> str:
    return v["prompt"]


# ---------- ツール一覧 ----------

TOOLS: list[Tool] = [
    Tool(
        name="ブログ記事作成",
        icon="📝",
        description="テーマを入力するだけで、見出し構成付きのブログ記事を執筆します。",
        system_instruction=BLOG_SYSTEM,
        fields=[
            Field("topic", "記事のテーマ", "text", "例: 在宅ワークを快適にするデスク環境の作り方", required=True),
            Field("main_keyword", "メインキーワード（任意）", "text", "例: 在宅ワーク デスク環境"),
            Field("keywords", "関連キーワード（任意）", "text", "例: 昇降デスク, モニターアーム, 腰痛対策"),
            Field("intent", "検索意図", "select", options=[
                "AIにおまかせ（キーワードから推測する）",
                "知りたい（情報収集・意味を知りたい）",
                "やり方を知りたい（手順・方法）",
                "比較したい（おすすめ・違い・選び方）",
                "買いたい・申し込みたい（購入直前）",
            ]),
            Field("audience", "想定読者（任意）", "text", "例: 在宅ワークを始めたばかりの会社員"),
            Field("tone", "文体", "select", options=["です・ます調", "だ・である調", "カジュアル", "専門的"]),
            Field("length", "文字数の目安", "slider", default=2000, min_value=500, max_value=6000, step=500),
            EXTRA_FIELD,
        ],
        build_prompt=blog_prompt,
        temperature=0.8,
    ),
    Tool(
        name="メール返信作成",
        icon="✉️",
        description="受信したメールを貼り付けると、適切な返信文を考えます。",
        system_instruction=BASE_SYSTEM + " ビジネスマナーに精通しており、相手に配慮した分かりやすいメールを書けます。",
        fields=[
            Field("received", "受信したメール", "textarea", "ここに受信したメールを貼り付けてください", required=True),
            Field("intent", "返信で伝えたいこと（任意）", "textarea", "例: 日程は了承。資料は金曜までに送る", height=100),
            Field("relation", "相手との関係", "select", options=["取引先・顧客", "社内の上司", "社内の同僚", "友人・知人", "初対面の相手"]),
            Field("tone", "文体", "select", options=TONES),
            EXTRA_FIELD,
        ],
        build_prompt=email_prompt,
        temperature=0.5,
    ),
    Tool(
        name="文章要約",
        icon="📋",
        description="長い文章のポイントを押さえて、短くまとめます。",
        system_instruction=BASE_SYSTEM + " 文章の要点を正確に抽出し、元の意味を損なわずに簡潔にまとめるのが得意です。",
        fields=[
            Field("text", "要約したい文章", "textarea", "ここに文章を貼り付けてください", required=True, height=300),
            Field("style", "要約形式", "select", options=["箇条書き", "文章（段落）", "3行まとめ", "見出し付きレポート"]),
            Field("length", "長さ", "select", options=["短め（元の1割程度）", "普通（元の2〜3割程度）", "詳しめ（元の半分程度）"]),
            EXTRA_FIELD,
        ],
        build_prompt=summary_prompt,
        temperature=0.3,
    ),
    Tool(
        name="文章校正・リライト",
        icon="✏️",
        description="誤字脱字のチェックや、より良い表現への書き換えを行います。",
        system_instruction=BASE_SYSTEM + " 校正・校閲の専門家として、自然で読みやすい日本語に整えます。",
        fields=[
            Field("text", "対象の文章", "textarea", "ここに文章を貼り付けてください", required=True, height=300),
            Field("mode", "モード", "select", options=[
                "誤字脱字・文法のみ校正",
                "読みやすくリライト",
                "より丁寧な表現にリライト",
                "よりカジュアルな表現にリライト",
                "簡潔に短くリライト",
            ]),
            EXTRA_FIELD,
        ],
        build_prompt=proofread_prompt,
        temperature=0.4,
    ),
    Tool(
        name="翻訳",
        icon="🌐",
        description="自然な表現で多言語に翻訳します。",
        system_instruction="あなたはプロの翻訳者です。原文のニュアンスを保ちつつ、翻訳先の言語として自然な文章にしてください。",
        fields=[
            Field("text", "翻訳したい文章", "textarea", "ここに文章を貼り付けてください", required=True),
            Field("target", "翻訳先の言語", "select", options=["英語", "日本語", "中国語（簡体字）", "韓国語", "スペイン語", "フランス語", "ドイツ語"]),
            Field("style", "翻訳スタイル", "select", options=["自然な意訳", "原文に忠実な直訳", "ビジネス向け", "カジュアル"]),
            EXTRA_FIELD,
        ],
        build_prompt=translate_prompt,
        temperature=0.3,
    ),
    Tool(
        name="SNS投稿作成",
        icon="📱",
        description="X・Instagram などに合わせた投稿文を複数パターン作成します。",
        system_instruction=BASE_SYSTEM + " SNSマーケティングに詳しく、反応を得やすい投稿文を作れます。",
        fields=[
            Field("content", "投稿したい内容", "textarea", "例: 新しいブログ記事を公開した。テーマは在宅ワークのデスク環境", required=True, height=120),
            Field("platform", "プラットフォーム", "select", options=["X (Twitter)", "Instagram", "Threads", "Facebook", "LinkedIn", "note"]),
            Field("tone", "文体", "select", options=TONES),
            Field("count", "パターン数", "slider", default=3, min_value=1, max_value=5),
            EXTRA_FIELD,
        ],
        build_prompt=sns_prompt,
        temperature=0.9,
    ),
    Tool(
        name="タイトル・キャッチコピー",
        icon="💡",
        description="記事タイトル・メール件名・キャッチコピーの案を大量に出します。",
        system_instruction=BASE_SYSTEM + " 人の興味を引くコピーライティングが得意です。",
        fields=[
            Field("content", "内容・概要", "textarea", "例: 初心者向けにPythonの始め方を解説する記事", required=True, height=120),
            Field("kind", "種類", "select", options=["ブログ記事タイトル", "メール件名", "キャッチコピー", "YouTube動画タイトル", "商品名・サービス名"]),
            Field("count", "案の数", "slider", default=10, min_value=3, max_value=20),
            EXTRA_FIELD,
        ],
        build_prompt=title_prompt,
        temperature=1.0,
    ),
    Tool(
        name="アイデア出し",
        icon="🧠",
        description="ブログのネタや企画など、アイデアをブレインストーミングします。",
        system_instruction=BASE_SYSTEM + " 発想力豊かな企画のプロです。",
        fields=[
            Field("theme", "テーマ", "text", "例: 個人ブログで書けるネタ（ジャンル: ガジェット）", required=True),
            Field("purpose", "目的・用途（任意）", "text", "例: 月10本の記事ネタを確保したい"),
            Field("count", "アイデアの数", "slider", default=10, min_value=3, max_value=30),
            EXTRA_FIELD,
        ],
        build_prompt=idea_prompt,
        temperature=1.0,
    ),
    Tool(
        name="フリープロンプト",
        icon="💬",
        description="上記に当てはまらない依頼を自由に入力できます。",
        system_instruction="あなたは優秀な日本語アシスタントです。回答は Markdown で分かりやすく出力してください。",
        fields=[
            Field("prompt", "依頼内容", "textarea", "AIにお願いしたいことを自由に書いてください", required=True, height=250),
        ],
        build_prompt=free_prompt,
        temperature=0.7,
    ),
]
