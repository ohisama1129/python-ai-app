"""Gemini API との通信を担当するモジュール。"""

from collections.abc import Iterator

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-3.8-flash"

# API からモデル一覧を取得できなかった場合の選択肢
FALLBACK_MODELS = [DEFAULT_MODEL]


def list_models(api_key: str) -> list[str]:
    """API キーで利用できるテキスト生成モデルの一覧を返す（既定モデルを先頭に）。"""
    client = genai.Client(api_key=api_key)
    names = sorted(
        m.name.removeprefix("models/")
        for m in client.models.list()
        if "generateContent" in (m.supported_actions or [])
        and m.name.removeprefix("models/").startswith("gemini-")
    )
    if DEFAULT_MODEL in names:
        names.remove(DEFAULT_MODEL)
        names.insert(0, DEFAULT_MODEL)
    return names or FALLBACK_MODELS


def stream_generate(
    api_key: str,
    model: str,
    system_instruction: str,
    prompt: str,
    temperature: float = 0.7,
) -> Iterator[str]:
    """プロンプトを送信し、生成されたテキストを少しずつ返す。"""
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
    )
    for chunk in client.models.generate_content_stream(
        model=model, contents=prompt, config=config
    ):
        if chunk.text:
            yield chunk.text
