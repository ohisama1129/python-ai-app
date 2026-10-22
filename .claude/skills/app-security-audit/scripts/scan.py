"""Streamlit + LLM API アプリの機械的なセキュリティチェック（標準ライブラリのみ）。

使い方:
    python scan.py <プロジェクトのルート> [--audit]

--audit を付けると、pip-audit が使える場合に依存ライブラリの既知脆弱性も調べる。
秘密情報の値そのものは決して表示しない（先頭4文字＋長さのみ）。
結果は「手がかり」であり、最終判断はコードを読んで行うこと。
"""

import re
import shutil
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

SKIP_DIRS = {".venv", "venv", "env", ".git", "__pycache__", "node_modules", ".agents", ".claude",
             ".mypy_cache", ".pytest_cache", "site-packages", "dist", "build"}
TEXT_SUFFIXES = {".py", ".toml", ".txt", ".md", ".json", ".yaml", ".yml", ".cfg", ".ini",
                 ".env", ".example", ".sh", ".ipynb", ""}
SECRET_FILES = {".env", "secrets.toml"}  # ここに秘密情報があるのは想定どおり（Git管理外なら）

# 長い・具体的なパターンを先に置く（同じ箇所を二重に報告しないため）
SECRET_PATTERNS = [
    ("Anthropic API キー", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API キー", re.compile(r"sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}")),
    ("Google/Gemini API キー", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("Groq API キー", re.compile(r"gsk_[A-Za-z0-9]{20,}")),
    ("xAI API キー", re.compile(r"xai-[A-Za-z0-9]{20,}")),
    ("Hugging Face トークン", re.compile(r"hf_[A-Za-z0-9]{20,}")),
    ("Replicate トークン", re.compile(r"r8_[A-Za-z0-9]{20,}")),
    ("AWS アクセスキー", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("秘密鍵", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("代入された秘密情報らしき値",
     re.compile(r"""(?i)\b\w*(?:api_?key|secret|token|password)\w*\s*[:=]\s*["']([A-Za-z0-9_\-\.]{16,})["']""")),
]
PLACEHOLDERS = {"", "xxx", "changeme", "your-api-key-here", "your_api_key", "sk-...", "<your-key>"}

LLM_SDKS = {
    "openai": "OpenAI", "anthropic": "Anthropic", "google.genai": "Gemini (google-genai)",
    "google.generativeai": "Gemini (旧SDK)", "vertexai": "Vertex AI", "mistralai": "Mistral",
    "cohere": "Cohere", "groq": "Groq", "ollama": "Ollama", "litellm": "LiteLLM",
    "langchain": "LangChain", "llama_index": "LlamaIndex", "boto3": "AWS (Bedrock?)",
}

# (正規表現, 重要度, 説明)
CODE_PATTERNS = [
    (r"unsafe_allow_html\s*=\s*True", "HIGH", "unsafe_allow_html=True：渡す値にLLM出力やユーザー入力が含まれるとXSS"),
    (r"\bst\.html\(|components\.(v1\.)?html\(|components\.iframe\(", "HIGH", "生HTML/iframeの描画：信頼できない値が含まれないか確認"),
    (r"\b(eval|exec)\(", "HIGH", "eval/exec：入力やLLM出力を実行していないか確認"),
    (r"\bos\.system\(|subprocess\.|shell\s*=\s*True", "MEDIUM", "外部コマンド実行：入力値やLLM出力が混ざらないか確認"),
    (r"\bpickle\.loads?\(|yaml\.load\((?!.*SafeLoader)|torch\.load\(", "MEDIUM", "安全でないデシリアライズ"),
    (r"\.execute\(\s*f[\"']|\.execute\([^)]*%\s|\.execute\([^)]*\.format\(", "HIGH", "SQLを文字列で組み立てている：SQLインジェクション"),
    (r"requests\.(get|post)\(|httpx\.(get|post)|urlopen\(", "INFO", "外部URL取得：URLにユーザー入力やLLM出力が入るならSSRFに注意"),
    (r"st\.file_uploader\(", "INFO", "ファイルアップロード：中身をLLMに渡すなら間接プロンプトインジェクション、保存するならパス・サイズに注意"),
    (r"\btools\s*=|function_call|tool_choice|\.bind_tools\(|create_react_agent|AgentExecutor", "INFO",
     "ツール呼び出し/エージェント：LLMに許可している操作の範囲を確認（過剰な権限）"),
    (r"st\.(error|exception|write)\(.*\{e\}|st\.exception\(", "LOW", "例外メッセージを画面にそのまま表示：内部情報が漏れないか確認"),
    (r"(print|logging\.\w+|logger\.\w+)\(.*(api_?key|secret|token|password)", "MEDIUM", "秘密情報をログ出力している可能性"),
    (r"@st\.cache_(data|resource)", "INFO", "キャッシュ：全ユーザー共有。ユーザー固有データや秘密情報を入れていないか確認"),
    (r"st\.(markdown|write|chat_message)\(", "INFO", "Markdown描画：LLM出力なら外部画像URL経由の情報持ち出しに注意"),
    (r"\bmax_(output_)?tokens\b", "OK", None),  # 出力上限の有無の判定に使う
    (r"st\.login\(|st\.user\b|st\.experimental_user|streamlit_authenticator", "OK", None),  # 認証の有無の判定に使う
]

findings: list[tuple[str, str, str]] = []  # (重要度, 場所, 内容)
signals: set[str] = set()


def add(level: str, where: str, msg: str):
    findings.append((level, where, msg))


def mask(s: str) -> str:
    return f"{s[:4]}…（{len(s)}文字）"


def iter_files(root: Path):
    for p in root.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.is_file() and (p.suffix in TEXT_SUFFIXES or p.name.startswith(".env")):
            yield p


def read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def check_secrets(root: Path):
    for p in iter_files(root):
        text = read(p)
        if text is None:
            continue
        rel = p.relative_to(root)
        expected = p.name in SECRET_FILES or (p.name.startswith(".env") and p.suffix != ".example")
        seen: set[int] = set()
        for name, pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                g = 1 if m.groups() else 0
                value, start = m.group(g), m.start(g)
                if start in seen or value.lower() in PLACEHOLDERS:
                    continue
                seen.add(start)
                line = text.count("\n", 0, m.start()) + 1
                if expected:
                    add("INFO", f"{rel}:{line}", f"{name} {mask(value)}（秘密情報用ファイル内：Git管理外なら想定どおり）")
                else:
                    add("HIGH", f"{rel}:{line}", f"{name} {mask(value)}：コードや共有ファイルに秘密情報が直書きされている")


def is_ignored(root: Path, rel: str) -> bool:
    if (root / ".git").exists() and shutil.which("git"):
        r = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", rel])
        return r.returncode == 0
    gi = root / ".gitignore"
    if not gi.exists():
        return False
    name = Path(rel).name
    pats = {l.strip().lstrip("/") for l in gi.read_text().splitlines() if l.strip() and not l.startswith("#")}
    return bool(pats & {rel, name, ".env*", "*.env", ".streamlit/", ".streamlit/*", "secrets.toml", "*.toml"})


def check_secret_files(root: Path):
    candidates = [".env", ".streamlit/secrets.toml"] + [p.name for p in root.glob(".env.*") if p.suffix != ".example"]
    for rel in dict.fromkeys(candidates):
        p = root / rel
        if not is_ignored(root, rel):
            level = "HIGH" if p.exists() else "LOW"
            add(level, ".gitignore", f"{rel} が .gitignore で除外されていない：Git に push すると秘密情報が流出する")
        if (root / ".git").exists() and shutil.which("git"):
            r = subprocess.run(["git", "-C", str(root), "ls-files", rel], capture_output=True, text=True)
            if r.stdout.strip():
                add("HIGH", rel, "Git で追跡されている（git rm --cached と、キーの再発行が必要。履歴にも残っている）")
        if p.exists():
            mode = stat.S_IMODE(p.stat().st_mode)
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                add("LOW", rel, f"パーミッションが {oct(mode)}：同じPCの他ユーザーから読める（chmod 600 推奨）")
    example = root / ".env.example"
    if example.exists():
        for line in example.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                v = v.strip().strip("\"'")
                if v.lower() not in PLACEHOLDERS and not re.fullmatch(r"(your|<|xxx|sk-\.\.\.).*", v, re.I):
                    add("MEDIUM", ".env.example", f"{k.strip()} にプレースホルダ以外の値が入っている（本物の値でないか確認）")


def check_streamlit_config(root: Path):
    configs = [root / ".streamlit" / "config.toml", Path.home() / ".streamlit" / "config.toml"]
    server: dict = {}
    found = []
    for c in reversed(configs):  # プロジェクト側を優先して上書き
        if c.exists():
            found.append(str(c))
            try:
                server |= tomllib.loads(c.read_text()).get("server", {})
            except tomllib.TOMLDecodeError as e:
                add("LOW", str(c), f"TOML を読めない: {e}")
    where = ", ".join(found) or "（config.toml なし＝既定値）"
    addr = server.get("address")
    if addr in (None, "", "0.0.0.0", "::"):
        auth = "（認証の実装は見つかった）" if "auth" in signals else "（認証の実装も見つからない）"
        add("MEDIUM", where,
            f"server.address が未指定/全インターフェース：同じネットワークの他の端末からアプリを開ける{auth}。"
            "ローカル利用なら .streamlit/config.toml に [server] address = \"localhost\"")
    if server.get("enableXsrfProtection") is False:
        add("MEDIUM", where, "enableXsrfProtection = false：XSRF 保護が無効")
    if server.get("enableCORS") is False:
        add("LOW", where, "enableCORS = false：CORS 保護が無効")
    if server.get("maxUploadSize", 200) > 200:
        add("LOW", where, f"maxUploadSize = {server['maxUploadSize']}MB：大きなファイルでメモリやLLMコストを消費されうる")


def check_code(root: Path):
    sdks: set[str] = set()
    for p in iter_files(root):
        if p.suffix != ".py":
            continue
        text = read(p) or ""
        rel = p.relative_to(root)
        for mod, label in LLM_SDKS.items():
            if re.search(rf"^\s*(from|import)\s+{re.escape(mod)}\b", text, re.M):
                sdks.add(label)
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for pat, level, msg in CODE_PATTERNS:
                if re.search(pat, line):
                    if level == "OK":
                        signals.add("max_tokens" if "max_" in pat else "auth")
                    else:
                        add(level, f"{rel}:{i}", msg)
    add("INFO", "構成", f"検出したLLM SDK: {', '.join(sorted(sdks)) or 'なし（HTTP直叩きの可能性）'}")
    if sdks and "max_tokens" not in signals:
        add("LOW", "構成", "出力トークン上限（max_tokens 等）の指定が見つからない：公開時はコスト上限の観点で確認")
    if "auth" not in signals:
        add("INFO", "構成", "認証（st.login / st.user 等）の実装が見つからない：公開・共有するなら必要")


def check_requirements(root: Path, audit: bool):
    req = root / "requirements.txt"
    if req.exists():
        unpinned = [l.strip() for l in req.read_text().splitlines()
                    if l.strip() and not l.startswith(("#", "-")) and "==" not in l]
        if unpinned:
            add("LOW", "requirements.txt", f"バージョン未固定: {', '.join(unpinned)}（再インストール時に別バージョンが入る）")
    elif not (root / "pyproject.toml").exists():
        add("INFO", "依存関係", "requirements.txt / pyproject.toml がない")
    if not audit:
        return
    venv_py = next((root / d / "bin" / "python" for d in (".venv", "venv", "env")
                    if (root / d / "bin" / "python").exists()), None)
    py = str(venv_py) if venv_py else sys.executable
    r = subprocess.run([py, "-m", "pip_audit", "--format", "columns"], capture_output=True, text=True)
    if "No module named" in r.stderr:
        add("INFO", "依存関係", f"pip-audit 未インストールのため脆弱性DBとの照合は未実施（{py} -m pip install pip-audit）")
    elif r.returncode == 0:
        add("INFO", "依存関係", "pip-audit：既知の脆弱性なし")
    else:
        add("HIGH", "依存関係", "pip-audit が既知の脆弱性を検出:\n" + (r.stdout or r.stderr).strip())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0] if args else ".").resolve()
    check_code(root)  # 先に実行して signals を集める
    check_secrets(root)
    check_secret_files(root)
    check_streamlit_config(root)
    check_requirements(root, "--audit" in sys.argv)

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    print(f"# 自動スキャン結果: {root}\n")
    for level, where, msg in sorted(findings, key=lambda f: order[f[0]]):
        print(f"[{level}] {where}\n    {msg}")
    counts = {k: sum(f[0] == k for f in findings) for k in order}
    print("\n集計: " + " / ".join(f"{k} {v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
