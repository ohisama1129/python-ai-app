"""AIライティングツール（Streamlit + Gemini API）"""

import os
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

from gemini_client import FALLBACK_MODELS, list_models, stream_generate
from tools import TOOLS, Field, Tool

load_dotenv()

st.set_page_config(
    page_title="AIライティングツール",
    page_icon="✍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

@st.cache_data(ttl=3600, show_spinner=False)
def get_models(api_key: str) -> list[str]:
    try:
        return list_models(api_key)
    except Exception:
        return FALLBACK_MODELS


if "results" not in st.session_state:
    st.session_state.results = {}  # ツール名 -> 最新の生成結果
if "history" not in st.session_state:
    st.session_state.history = []  # 生成履歴（アプリを閉じると消える）


# ---------- サイドバー ----------

with st.sidebar:
    st.title("✍️ AIライティング")

    tool_name = st.radio(
        "ツールを選択",
        [t.name for t in TOOLS],
        format_func=lambda n: next(f"{t.icon} {t.name}" for t in TOOLS if t.name == n),
    )
    tool: Tool = next(t for t in TOOLS if t.name == tool_name)

    st.divider()
    st.subheader("⚙️ 設定")
    api_key = os.getenv("GEMINI_API_KEY", "")
    if api_key == "your-api-key-here":  # .env.example のままの場合は未設定扱い
        api_key = ""
    if not api_key:
        api_key = st.text_input("Gemini API キー", type="password", help=".env に GEMINI_API_KEY を設定すると入力不要になります")
    model = st.selectbox(
        "モデル",
        get_models(api_key) if api_key else FALLBACK_MODELS,
        help="APIキーで利用できるモデルの一覧です",
    )
    temperature = st.slider(
        "創造性（temperature）", 0.0, 2.0, tool.temperature, 0.1,
        key=f"temp:{tool.name}",
        help="低いほど正確・安定、高いほど自由・多様な文章になります",
    )

    st.divider()
    st.caption(f"📜 履歴: {len(st.session_state.history)} 件")
    if st.session_state.history and st.button("履歴をクリア", use_container_width=True):
        st.session_state.history = []
        st.session_state.results = {}
        st.rerun()


# ---------- 入力フォーム ----------

def render_field(f: Field, tool: Tool):
    key = f"{tool.name}:{f.key}"
    if f.kind == "textarea":
        return st.text_area(f.label, placeholder=f.placeholder, height=f.height, key=key)
    if f.kind == "select":
        return st.selectbox(f.label, f.options, key=key)
    if f.kind == "slider":
        return st.slider(f.label, f.min_value, f.max_value, f.default, f.step, key=key)
    return st.text_input(f.label, placeholder=f.placeholder, key=key)


def run(system_instruction: str, prompt: str) -> str | None:
    """Gemini で生成し、結果をストリーミング表示して返す。"""
    if not api_key:
        st.error("Gemini API キーを設定してください（サイドバーまたは .env）。")
        return None
    try:
        with st.container(border=True):
            return st.write_stream(stream_generate(api_key, model, system_instruction, prompt, temperature))
    except Exception as e:
        st.error(f"生成中にエラーが発生しました: {e}")
        return None


def save_result(text: str, prompt: str):
    st.session_state.results[tool.name] = {"text": text, "prompt": prompt}
    st.session_state.history.insert(0, {
        "tool": f"{tool.icon} {tool.name}",
        "time": datetime.now().strftime("%H:%M:%S"),
        "text": text,
    })


st.header(f"{tool.icon} {tool.name}")
st.caption(tool.description)

col_input, col_output = st.columns([1, 1], gap="large")

with col_input:
    values = {f.key: render_field(f, tool) for f in tool.fields}
    generate = st.button("✨ 生成する", type="primary", use_container_width=True)

with col_output:
    st.subheader("出力")
    if generate:
        missing = [f.label for f in tool.fields if f.required and not str(values[f.key]).strip()]
        if missing:
            st.warning(f"「{'」「'.join(missing)}」を入力してください。")
        else:
            prompt = tool.build_prompt(values)
            with st.spinner("生成中..."):
                text = run(tool.system_instruction, prompt)
            if text:
                save_result(text, prompt)
                st.rerun()

    result = st.session_state.results.get(tool.name)
    if result:
        with st.container(border=True):
            st.markdown(result["text"])

        with st.expander("📄 コピー用テキスト"):
            st.code(result["text"], language="markdown", wrap_lines=True)

        st.download_button(
            "⬇️ Markdown でダウンロード",
            result["text"],
            file_name=f"{tool.name}_{datetime.now():%Y%m%d_%H%M%S}.md",
            mime="text/markdown",
            use_container_width=True,
        )

        # 生成結果に追加の指示を出して修正する
        st.markdown("##### 🔁 修正を依頼する")
        with st.form(key=f"refine:{tool.name}", clear_on_submit=True):
            instruction = st.text_input("修正指示", placeholder="例: もっと短く / 結論を先に / 具体例を追加して")
            refine = st.form_submit_button("修正する", use_container_width=True)
        if refine and instruction.strip():
            refine_prompt = f"""以下は先ほどの依頼と、あなたの出力です。

# 元の依頼
{result['prompt']}

# あなたの出力
{result['text']}

# 修正指示
{instruction}

修正指示に従って出力全体を書き直してください。"""
            with st.spinner("修正中..."):
                text = run(tool.system_instruction, refine_prompt)
            if text:
                save_result(text, refine_prompt)
                st.rerun()
    elif not generate:
        st.info("左側のフォームに入力して「生成する」を押してください。")


# ---------- 履歴 ----------

if st.session_state.history:
    st.divider()
    st.subheader("📜 生成履歴")
    for i, h in enumerate(st.session_state.history):
        with st.expander(f"{h['time']}  {h['tool']}  —  {h['text'][:40].replace(chr(10), ' ')}…"):
            st.markdown(h["text"])
