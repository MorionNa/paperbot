from __future__ import annotations

import calendar
import json
import re
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from datetime import date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import yaml
from app.gui_style import apply_theme, BG_MAIN, BG_PANEL, BORDER, TEXT_MAIN

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config" / "config.yml"
SECRETS_PATH = BASE_DIR / "config" / "secrets.yml"
PUBLISHERS = ["elsevier", "wiley", "springer", "ieee", "other"]
SUMMARY_API_PROVIDERS = {
    # UI选项: (llm.provider, api_key_env, secret_key, 默认base_url, base_url_secret_key)
    "chatgpt": ("chatgpt", "OPENAI_API_KEY", "openai_api_key", "https://api.openai.com/v1", "chatgpt_base_url"),
    "gemini": ("gemini", "GEMINI_API_KEY", "gemini_api_key", "", "gemini_base_url"),
    "claude": ("claude", "ANTHROPIC_API_KEY", "anthropic_api_key", "", "claude_base_url"),
    "千问": ("qwen", "DASHSCOPE_API_KEY", "dashscope_api_key", "https://dashscope.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1", "qwen_base_url"),
    "元宝": ("yuanbao", "YUANBAO_API_KEY", "yuanbao_api_key", "", "yuanbao_base_url"),
    "deepseek": ("deepseek", "DEEPSEEK_API_KEY", "deepseek_api_key", "https://api.deepseek.com/v1", "deepseek_base_url"),
    "智谱": ("zhipu", "ZHIPU_API_KEY", "zhipu_api_key", "https://open.bigmodel.cn/api/paas/v4", "zhipu_base_url"),
    "custom": ("custom", "CUSTOM_LLM_API_KEY", "custom_llm_api_key", "", "custom_base_url"),
}

PROVIDER_TO_UI = {v[0]: k for k, v in SUMMARY_API_PROVIDERS.items()}


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def _save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _keywords_json_to_text(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        obj = json.loads(raw)
        if isinstance(obj, list):
            return "; ".join(str(x) for x in obj if str(x).strip())
        return str(obj)
    except Exception:
        return raw




def _split_keywords(keyword_text: str) -> list[str]:
    raw = (keyword_text or "").strip()
    if not raw:
        return []
    parts = [x.strip() for x in raw.replace("、", ";").split(";")]
    return [x for x in parts if x]


def _append_journal(name: str, publisher: str, issn_print: str, issn_online: str) -> None:
    cfg = _load_yaml(CONFIG_PATH)
    journals = cfg.setdefault("journals", [])
    journal = {"name": name.strip(), "publisher": publisher.strip().lower()}
    if issn_print.strip():
        journal["issn_print"] = issn_print.strip()
    if issn_online.strip():
        journal["issn_online"] = issn_online.strip()
    if not journal.get("crossref_issn"):
        if issn_online.strip():
            journal["crossref_issn"] = issn_online.strip()
        elif issn_print.strip():
            journal["crossref_issn"] = issn_print.strip()
    journals.append(journal)
    _save_yaml(CONFIG_PATH, cfg)


def _delete_journal(index: int) -> None:
    cfg = _load_yaml(CONFIG_PATH)
    journals = cfg.get("journals") or []
    if 0 <= index < len(journals):
        journals.pop(index)
    cfg["journals"] = journals
    _save_yaml(CONFIG_PATH, cfg)


def _get_journals() -> list[dict]:
    cfg = _load_yaml(CONFIG_PATH)
    return list(cfg.get("journals") or [])


def _save_provider_api_keys(elsevier_key: str, wiley_key: str, springer_key: str, ieee_key: str) -> None:
    secrets = _load_yaml(SECRETS_PATH)
    if elsevier_key.strip():
        secrets["elsevier_api_key"] = elsevier_key.strip()
    if wiley_key.strip():
        secrets["wiley_tdm_client_token"] = wiley_key.strip()
    if springer_key.strip():
        secrets["springer_api_key"] = springer_key.strip()
    if ieee_key.strip():
        secrets["ieee_api_key"] = ieee_key.strip()
    _save_yaml(SECRETS_PATH, secrets)


def _save_summary_llm_config(provider: str, base_url: str, api_key: str, max_tokens: str) -> None:
    cfg = _load_yaml(CONFIG_PATH)
    llm = cfg.setdefault("llm", {})
    gui = cfg.setdefault("gui", {})
    summary_base_urls = gui.setdefault("summary_base_urls", {})

    selected = provider if provider in SUMMARY_API_PROVIDERS else "custom"
    llm_provider, env_name, secret_key, default_base_url, _base_url_secret_key = SUMMARY_API_PROVIDERS[selected]

    normalized_base_url = (base_url or "").strip() or default_base_url
    llm["provider"] = llm_provider
    llm["base_url"] = normalized_base_url
    llm["api_key_env"] = env_name
    summary_base_urls[selected] = normalized_base_url

    if max_tokens.strip():
        llm["max_output_tokens"] = int(max_tokens.strip())
    _save_yaml(CONFIG_PATH, cfg)

    secrets = _load_yaml(SECRETS_PATH)
    if api_key.strip():
        secrets[secret_key] = api_key.strip()
    _save_yaml(SECRETS_PATH, secrets)


def _get_saved_provider_fields(ui_provider: str, cfg: dict | None = None, sec: dict | None = None) -> tuple[str, str]:
    cfg = cfg or _load_yaml(CONFIG_PATH)
    sec = sec or _load_yaml(SECRETS_PATH)
    llm = cfg.get("llm") or {}
    gui = cfg.get("gui") or {}
    summary_base_urls = gui.get("summary_base_urls") or {}

    item = SUMMARY_API_PROVIDERS.get(ui_provider, SUMMARY_API_PROVIDERS["custom"])
    llm_provider, _env_name, secret_key, default_base_url, _base_url_secret_key = item

    raw_provider = str(llm.get("provider") or "").strip().lower()
    if raw_provider == llm_provider:
        base_url = str(llm.get("base_url") or "").strip()
    else:
        base_url = str(summary_base_urls.get(ui_provider) or "").strip()

    api_key = str(sec.get(secret_key) or "").strip()
    if not base_url:
        base_url = default_base_url
    return base_url, api_key




def _load_saved_gui_settings() -> dict:
    cfg = _load_yaml(CONFIG_PATH)
    sec = _load_yaml(SECRETS_PATH)
    llm = cfg.get("llm") or {}
    raw_provider = str(llm.get("provider") or "custom").strip().lower()
    ui_provider = PROVIDER_TO_UI.get(raw_provider, "custom")
    llm_provider, env_name, secret_key, _default_base_url, _base_url_secret_key = SUMMARY_API_PROVIDERS.get(ui_provider, SUMMARY_API_PROVIDERS["custom"])
    saved_base_url, saved_api_key = _get_saved_provider_fields(ui_provider, cfg=cfg, sec=sec)
    return {
        "elsevier_api_key": sec.get("elsevier_api_key", ""),
        "wiley_tdm_client_token": sec.get("wiley_tdm_client_token", ""),
        "springer_api_key": sec.get("springer_api_key", ""),
        "ieee_api_key": sec.get("ieee_api_key", ""),
        "summary_base_url": saved_base_url,
        "summary_max_tokens": str(llm.get("max_output_tokens", "") or ""),
        "summary_provider": ui_provider,
        "summary_api_key": saved_api_key,
        "summary_api_env": env_name,
        "summary_llm_provider": llm_provider,
    }

def _set_date_range(date_from: str, date_until: str) -> None:
    cfg = _load_yaml(CONFIG_PATH)
    pipeline = cfg.setdefault("pipeline", {})
    pipeline["date_from"] = date_from.strip()
    pipeline["date_until"] = date_until.strip()
    _save_yaml(CONFIG_PATH, cfg)


def _run_daily() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BASE_DIR / "app" / "run_daily.py")],
        cwd=BASE_DIR,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _get_db_path_from_cfg() -> Path:
    cfg = _load_yaml(CONFIG_PATH)
    db_url = ((cfg.get("pipeline") or {}).get("db_url") or "sqlite:///data/papers.db").strip()
    if db_url.startswith("sqlite:///"):
        rel = db_url.replace("sqlite:///", "", 1)
        return (BASE_DIR / rel).resolve()
    return (BASE_DIR / "data" / "papers.db").resolve()


def _load_downloaded_articles(limit: int = 300) -> list[tuple[str, str, str, str, str, str, str]]:
    db_path = _get_db_path_from_cfg()
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    try:
        try:
            rows = conn.execute(
                """
                SELECT
                  COALESCE(a.published_date, ''),
                  COALESCE(a.title, ''),
                  COALESCE(a.journal, ''),
                  f.doi,
                  COALESCE(f.status, ''),
                  CASE WHEN lower(COALESCE(s.status, ''))='ok' THEN '查看' ELSE '未总结' END,
                  COALESCE(s.keywords_json, '')
                FROM fulltexts f
                LEFT JOIN articles a ON a.doi = f.doi
                LEFT JOIN summaries s ON s.doi = f.doi
                WHERE lower(COALESCE(f.status, '')) IN ('ok', 'success', 'downloaded')
                ORDER BY COALESCE(f.downloaded_at, '') DESC, f.rowid DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            # 兼容部分历史/非标准库结构，退化到更宽松查询
            rows = conn.execute(
                """
                SELECT
                  COALESCE(a.published_date, ''),
                  COALESCE(a.title, ''),
                  COALESCE(a.journal, ''),
                  f.doi,
                  COALESCE(f.status, ''),
                  '未总结',
                  ''
                FROM fulltexts f
                LEFT JOIN articles a ON a.doi = f.doi
                ORDER BY COALESCE(f.downloaded_at, '') DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [(str(r[0] or ""), str(r[1] or ""), str(r[2] or ""), str(r[3] or ""), str(r[4] or ""), str(r[5] or ""), _keywords_json_to_text(str(r[6] or ""))) for r in rows]
    finally:
        conn.close()




def _normalize_doi(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return ""
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"):
        if v.startswith(prefix):
            v = v[len(prefix):].strip()
            break
    if v.startswith("doi:"):
        v = v[4:].strip()
    v = v.split("?", 1)[0].split("#", 1)[0].strip()
    return v.rstrip("/.")

def _load_summaries_for_dois(dois: list[str]) -> dict[str, dict]:
    normalized_dois = [_normalize_doi(x) for x in dois if _normalize_doi(x)]
    print(f"[GUI][summary] selected_dois(raw)={dois}")
    print(f"[GUI][summary] selected_dois(normalized)={normalized_dois}")
    if not normalized_dois:
        print("[GUI][summary] skip query: no valid DOI after normalization")
        return {}
    target_set = set(normalized_dois)
    db_path = _get_db_path_from_cfg()
    print(f"[GUI][summary] db_path={db_path} exists={db_path.exists()}")
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    try:
        # 读取 summaries 后在 Python 侧做 DOI 归一化匹配，兼容多种历史存储格式
        rows = conn.execute(
            """
            SELECT doi, model, method_summary, result_summary, status, error, summarized_at
            FROM summaries
            ORDER BY COALESCE(summarized_at, '') DESC, rowid DESC
            """
        ).fetchall()
        print(f"[GUI][summary] summaries rows in db={len(rows)}")
        out: dict[str, dict] = {}
        for doi, model, method_summary, result_summary, status, error, summarized_at in rows:
            raw_key = str(doi or "").strip()
            normalized_key = _normalize_doi(raw_key)
            if not normalized_key or normalized_key not in target_set:
                continue
            print(f"[GUI][summary] matched doi raw={raw_key} normalized={normalized_key} status={status}")
            record = {
                "model": model or "",
                "method_summary": method_summary or "",
                "result_summary": result_summary or "",
                "status": status or "",
                "error": error or "",
                "summarized_at": summarized_at or "",
            }
            out[raw_key] = record
            out[normalized_key] = record
            out[str(raw_key).lower()] = record
        print(f"[GUI][summary] matched records={len(out)}")
        return out
    finally:
        conn.close()


class PaperBotGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("论文库下载工具")
        self.root.geometry("1320x840")
        self.root.minsize(1160, 720)

        self.running = False
        self.download_total_expected = 0
        self.download_success_count = 0
        self.download_date_sort_desc = True
        self.download_rows_cache: list[tuple[str, str, str, str, str, str, str]] = []
        self.download_keyword_all: list[str] = []
        self.download_keyword_selected: set[str] = set()
        self.keyword_search_var = tk.StringVar()
        self.summary_link_labels: dict[str, tk.Label] = {}
        self.summary_link_font = tkfont.Font(family="Arial", size=10, underline=True)
        self.active_page = "download"
        self._build_styles()
        self._build_layout()
        self._load_saved_values_into_form()
        self.show_page("download")

    def _build_styles(self) -> None:
        apply_theme(self.root)

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="Main.TFrame")
        shell.pack(fill=tk.BOTH, expand=True)

        self.sidebar = ttk.Frame(shell, width=290, style="Sidebar.TFrame")
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        self.main = ttk.Frame(shell, style="Main.TFrame")
        self.main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_sidebar()
        self._build_pages()

    def _build_sidebar(self) -> None:
        ttk.Label(self.sidebar, text="论文库下载工具", background=BG_MAIN, font=("Arial", 20, "bold")).pack(anchor=tk.W, padx=26, pady=(28, 2))
        ttk.Label(self.sidebar, text="Paper Downloader", background=BG_MAIN, foreground="#64748b", font=("Arial", 13)).pack(anchor=tk.W, padx=26, pady=(0, 24))

        self.btn_download = ttk.Button(self.sidebar, text="📘  文献下载", command=lambda: self.show_page("download"))
        self.btn_download.pack(fill=tk.X, padx=18, pady=6)

        self.btn_summary = ttk.Button(self.sidebar, text="🧠  文献总结", command=lambda: self.show_page("summary"))
        self.btn_summary.pack(fill=tk.X, padx=18, pady=6)

        ttk.Label(self.sidebar, text="Version 1.0", background=BG_MAIN, foreground="#64748b", font=("Arial", 12)).pack(side=tk.BOTTOM, anchor=tk.W, padx=26, pady=20)

    def _build_pages(self) -> None:
        self.download_page = ttk.Frame(self.main, style="Main.TFrame")
        self.summary_page = ttk.Frame(self.main, style="Main.TFrame")

        self._build_download_page(self.download_page)
        self._build_summary_page(self.summary_page)


    def _load_saved_values_into_form(self) -> None:
        saved = _load_saved_gui_settings()

        self.elsevier_key.set(str(saved.get("elsevier_api_key", "") or ""))
        self.wiley_key.set(str(saved.get("wiley_tdm_client_token", "") or ""))
        self.springer_key.set(str(saved.get("springer_api_key", "") or ""))
        self.ieee_key.set(str(saved.get("ieee_api_key", "") or ""))

        self.summary_base_url.set(str(saved.get("summary_base_url", "") or ""))
        self.summary_provider.set(str(saved.get("summary_provider", "custom") or "custom"))
        self.summary_api_key.set(str(saved.get("summary_api_key", "") or ""))

        max_tokens = str(saved.get("summary_max_tokens", "") or "")
        if max_tokens:
            self.summary_max_tokens.set(max_tokens)

        self.on_summary_provider_change()

    def show_page(self, page: str) -> None:
        self.active_page = page
        self.download_page.pack_forget()
        self.summary_page.pack_forget()

        if page == "download":
            self.download_page.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)
            self.btn_download.configure(style="MenuActive.TButton")
            self.btn_summary.configure(style="Menu.TButton")
            self.refresh_journal_table()
        else:
            self.summary_page.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)
            self.btn_download.configure(style="Menu.TButton")
            self.btn_summary.configure(style="MenuActive.TButton")
            self.refresh_downloaded_articles_table()

    def _build_download_page(self, parent: ttk.Frame) -> None:
        upper = ttk.Frame(parent, style="Main.TFrame")
        upper.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(upper, text="期刊信息", padding=14, style="Card.TLabelframe")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        right = ttk.LabelFrame(upper, text="text and data mining API key管理", padding=14, style="Card.TLabelframe")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        self._build_journal_panel(left)
        self._build_provider_api_panel(right)

        bottom = ttk.LabelFrame(parent, text="下载任务", padding=14, style="Card.TLabelframe")
        bottom.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        self._build_download_task_panel(bottom)

    def _build_summary_page(self, parent: ttk.Frame) -> None:
        top = ttk.LabelFrame(parent, text="已下载文献", padding=14, style="Card.TLabelframe")
        top.pack(fill=tk.X, expand=False)

        cols = ("published", "title", "journal", "doi", "status", "summary_status", "keywords")
        self.downloaded_tree = ttk.Treeview(top, columns=cols, show="headings", height=8, selectmode="extended")
        self.downloaded_tree.heading("published", text="日期", command=lambda: self.sort_downloaded_by_date())
        self.downloaded_tree.heading("title", text="标题")
        self.downloaded_tree.heading("journal", text="期刊")
        self.downloaded_tree.heading("doi", text="DOI")
        self.downloaded_tree.heading("status", text="下载状态")
        self.downloaded_tree.heading("summary_status", text="是否已总结")
        self.downloaded_tree.heading("keywords", text="关键词")
        self.downloaded_tree.column("published", width=90, anchor=tk.CENTER)
        self.downloaded_tree.column("title", width=330)
        self.downloaded_tree.column("journal", width=180)
        self.downloaded_tree.column("doi", width=200)
        self.downloaded_tree.column("status", width=90, anchor=tk.CENTER)
        self.downloaded_tree.column("summary_status", width=90, anchor=tk.CENTER)
        self.downloaded_tree.column("keywords", width=260)

        ybar = ttk.Scrollbar(top, orient=tk.VERTICAL, command=self.downloaded_tree.yview)
        xbar = ttk.Scrollbar(top, orient=tk.HORIZONTAL, command=self.downloaded_tree.xview)
        self.downloaded_tree.configure(
            yscrollcommand=lambda first, last: self._on_tree_scrolled(ybar, first, last),
            xscrollcommand=lambda first, last: self._on_tree_scrolled(xbar, first, last),
        )
        self.downloaded_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        xbar.pack(side=tk.BOTTOM, fill=tk.X)
        ybar.pack(side=tk.RIGHT, fill=tk.Y)

        action_bar = ttk.Frame(parent)
        action_bar.pack(fill=tk.X, pady=(8, 0))
        self.summary_analyze_btn = ttk.Button(action_bar, text="智能分析", style="Primary.TButton", command=self.on_analyze_selected)
        self.summary_analyze_btn.pack(side=tk.LEFT)
        ttk.Button(action_bar, text="刷新文献", command=self.refresh_downloaded_articles_table).pack(side=tk.LEFT, padx=8)

        ttk.Label(action_bar, text="关键词筛选（可多选）").pack(side=tk.LEFT, padx=(16, 6))
        ttk.Label(action_bar, text="检索").pack(side=tk.LEFT, padx=(8, 4))
        keyword_search_entry = ttk.Entry(action_bar, textvariable=self.keyword_search_var, width=18)
        keyword_search_entry.pack(side=tk.LEFT)
        keyword_search_entry.bind("<KeyRelease>", lambda _e: self.on_keyword_search_change())
        self.download_keyword_listbox = tk.Listbox(action_bar, selectmode=tk.MULTIPLE, height=4, exportselection=False)
        self.download_keyword_listbox.pack(side=tk.LEFT)
        self.download_keyword_listbox.bind("<<ListboxSelect>>", self.on_keyword_listbox_select)
        ttk.Button(action_bar, text="清空关键词筛选", command=self.clear_keyword_filter).pack(side=tk.LEFT, padx=8)
        self.downloaded_tree.bind("<ButtonRelease-1>", self.on_downloaded_tree_click)
        self.downloaded_tree.bind("<Motion>", self.on_downloaded_tree_motion)
        self.downloaded_tree.bind("<Leave>", self.on_downloaded_tree_leave)
        self.downloaded_tree.bind("<Configure>", lambda _e: self.root.after_idle(self._refresh_summary_link_labels))

        cfg = ttk.LabelFrame(parent, text="大模型配置", padding=14, style="Card.TLabelframe")
        cfg.pack(fill=tk.X, pady=(14, 0))

        self.summary_base_url = tk.StringVar()
        self.summary_api_key = tk.StringVar()
        self.summary_provider = tk.StringVar(value="custom")
        self.summary_max_tokens = tk.StringVar(value="900")

        ttk.Label(cfg, text="API 提供商").grid(row=0, column=0, sticky=tk.W, pady=5)
        provider_box = ttk.Combobox(
            cfg,
            textvariable=self.summary_provider,
            values=list(SUMMARY_API_PROVIDERS.keys()),
            state="readonly",
            width=20,
        )
        provider_box.grid(row=0, column=1, sticky=tk.W, padx=8, pady=5)
        provider_box.bind("<<ComboboxSelected>>", lambda _e: self.on_summary_provider_change())

        ttk.Label(cfg, text="源地址 (base_url)").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg, textvariable=self.summary_base_url, width=78).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=5)

        ttk.Label(cfg, text="API Key").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg, textvariable=self.summary_api_key, width=78).grid(row=2, column=1, sticky=tk.EW, padx=8, pady=5)

        ttk.Label(cfg, text="最大输出 token").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(cfg, textvariable=self.summary_max_tokens, width=20).grid(row=3, column=1, sticky=tk.W, padx=8, pady=5)

        ttk.Button(cfg, text="确定", style="Success.TButton", command=self.on_save_summary_config).grid(row=4, column=1, sticky=tk.E, pady=(8, 0))
        cfg.columnconfigure(1, weight=1)

        out = ttk.LabelFrame(parent, text="总结结果", padding=14, style="Card.TLabelframe")
        out.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        self.summary_output = tk.Text(
            out,
            height=10,
            wrap="word",
            font=("Consolas", 10),
            bg="#FFFFFF",
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=10,
            pady=8,
        )
        self.summary_output.pack(fill=tk.BOTH, expand=True)

    def _build_journal_panel(self, parent: ttk.LabelFrame) -> None:
        form = ttk.Frame(parent)
        form.pack(fill=tk.X)

        self.journal_name = tk.StringVar()
        self.journal_publisher = tk.StringVar(value="elsevier")
        self.journal_issn_print = tk.StringVar()
        self.journal_issn_online = tk.StringVar()

        ttk.Label(form, text="期刊名称").grid(row=0, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_name, width=42).grid(row=0, column=1, sticky=tk.EW, padx=8, pady=6)
        ttk.Label(form, text="出版社").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Combobox(form, textvariable=self.journal_publisher, values=PUBLISHERS, state="readonly", width=39).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=6)
        ttk.Label(form, text="ISSN (print，可选)").grid(row=2, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_issn_print, width=42).grid(row=2, column=1, sticky=tk.EW, padx=8, pady=6)
        ttk.Label(form, text="ISSN (online，可选)").grid(row=3, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_issn_online, width=42).grid(row=3, column=1, sticky=tk.EW, padx=8, pady=6)
        form.columnconfigure(1, weight=1)

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(8, 10))
        ttk.Button(btn_row, text="＋ 添加", command=self.on_add_journal, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(btn_row, text="删除选中", command=self.on_delete_journal).pack(side=tk.LEFT, padx=8)

        ttk.Label(parent, text="已添加期刊", font=("Arial", 13, "bold")).pack(anchor=tk.W, pady=(4, 6))

        cols = ("name", "publisher", "issn")
        self.journal_tree = ttk.Treeview(parent, columns=cols, show="headings", height=9)
        self.journal_tree.heading("name", text="期刊名称")
        self.journal_tree.heading("publisher", text="出版社")
        self.journal_tree.heading("issn", text="ISSN")
        self.journal_tree.column("name", width=280)
        self.journal_tree.column("publisher", width=100, anchor=tk.CENTER)
        self.journal_tree.column("issn", width=110, anchor=tk.CENTER)

        ybar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.journal_tree.yview)
        self.journal_tree.configure(yscrollcommand=ybar.set)
        self.journal_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ybar.pack(side=tk.LEFT, fill=tk.Y)

    def _build_provider_api_panel(self, parent: ttk.LabelFrame) -> None:
        self.elsevier_key = tk.StringVar()
        self.wiley_key = tk.StringVar()
        self.springer_key = tk.StringVar()
        self.ieee_key = tk.StringVar()

        rows = [
            ("Elsevier API", self.elsevier_key, "https://dev.elsevier.com/apikey/manage"),
            ("Wiley API", self.wiley_key, "https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining"),
            ("Springer API", self.springer_key, "https://dev.springernature.com/"),
            ("IEEE API", self.ieee_key, "https://developer.ieee.org/"),
        ]

        for title, var, url in rows:
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=8)
            title_row = tk.Frame(row, bg=BG_PANEL)
            title_row.pack(fill=tk.X)
            tk.Label(title_row, text=title, font=("Arial", 12, "bold"), bg=BG_PANEL).pack(side=tk.LEFT)
            link = tk.Label(title_row, text=f"点我获取{title}", fg="#2563eb", cursor="hand2", font=("Arial", 10, "underline"), bg=BG_PANEL)
            link.pack(side=tk.LEFT, padx=(10, 0))
            link.bind("<Button-1>", lambda _e, u=url: self.open_api_link(u))

            entry_row = ttk.Frame(row)
            entry_row.pack(fill=tk.X, pady=(2, 0))
            ttk.Entry(entry_row, textvariable=var, width=42).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Label(entry_row, text="✅", foreground="#10b981", font=("Arial", 14)).pack(side=tk.LEFT, padx=8)

        ttk.Button(parent, text="✔ 保存", command=self.on_save_provider_keys, style="Success.TButton").pack(anchor=tk.E, pady=(18, 0))

    def _build_download_task_panel(self, parent: ttk.LabelFrame) -> None:
        grid = ttk.Frame(parent)
        grid.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(grid)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))

        ttk.Label(left, text="开始时间", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        self.date_from = tk.StringVar(value=(date.today() - timedelta(days=30)).isoformat())
        from_row = ttk.Frame(left)
        from_row.pack(anchor=tk.W, pady=(6, 12))
        ttk.Entry(from_row, textvariable=self.date_from, width=22, state="readonly").pack(side=tk.LEFT)
        ttk.Button(from_row, text="📅", width=3, command=lambda: self.open_calendar(self.date_from)).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(left, text="结束时间", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        self.date_until = tk.StringVar(value=date.today().isoformat())
        until_row = ttk.Frame(left)
        until_row.pack(anchor=tk.W, pady=(6, 12))
        ttk.Entry(until_row, textvariable=self.date_until, width=22, state="readonly").pack(side=tk.LEFT)
        ttk.Button(until_row, text="📅", width=3, command=lambda: self.open_calendar(self.date_until)).pack(side=tk.LEFT, padx=(6, 0))

        btns = ttk.Frame(left)
        btns.pack(anchor=tk.W, pady=(6, 4))
        self.start_btn = ttk.Button(btns, text="⬇ 开始下载", command=self.on_run_download, style="Primary.TButton")
        self.start_btn.pack(side=tk.LEFT)
        ttk.Button(btns, text="■ 清空日志", command=self.clear_logs).pack(side=tk.LEFT, padx=8)

        right = ttk.Frame(grid)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(right, text="任务日志", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        self.output_box = tk.Text(right, height=11, wrap="word", font=("Consolas", 11), bg="#FFFFFF", fg=TEXT_MAIN, insertbackground=TEXT_MAIN, relief="flat", highlightthickness=1, highlightbackground=BORDER, padx=10, pady=8)
        self.output_box.pack(fill=tk.BOTH, expand=True, pady=(6, 8))

        self.progress_var = tk.IntVar(value=0)
        self.progress = ttk.Progressbar(right, orient=tk.HORIZONTAL, maximum=100, variable=self.progress_var)
        self.progress.pack(fill=tk.X)
        self.progress_label = ttk.Label(right, text="总进度 0%")
        self.progress_label.pack(anchor=tk.E, pady=(4, 0))

    def log(self, text: str) -> None:
        self.output_box.insert(tk.END, text + "\n")
        self.output_box.see(tk.END)

    def clear_logs(self) -> None:
        self.output_box.delete("1.0", tk.END)
        self.progress_var.set(0)
        self.progress_label.config(text="总进度 0%")
        self.download_total_expected = 0
        self.download_success_count = 0

    def refresh_journal_table(self) -> None:
        for item in self.journal_tree.get_children():
            self.journal_tree.delete(item)
        for idx, j in enumerate(_get_journals()):
            issn_print = (j.get("issn_print") or "").strip()
            issn_online = (j.get("issn_online") or "").strip()
            if issn_print and issn_online:
                issn = f"P:{issn_print} / O:{issn_online}"
            else:
                issn = issn_print or issn_online or (j.get("crossref_issn") or "")
            self.journal_tree.insert("", tk.END, iid=str(idx), values=(j.get("name", ""), (j.get("publisher") or "").capitalize(), issn))

    def refresh_downloaded_articles_table(self) -> None:
        try:
            self.download_rows_cache = _load_downloaded_articles()
        except Exception as e:
            self.log(f"• 读取文献列表失败：{e}")
            self.download_rows_cache = []

        kws = sorted({kw for row in self.download_rows_cache for kw in _split_keywords(row[6])})
        self.download_keyword_all = kws
        self.download_keyword_selected = {kw for kw in self.download_keyword_selected if kw in set(kws)}
        if hasattr(self, "download_keyword_listbox"):
            self._render_keyword_listbox()

        self._render_downloaded_rows()

    def _render_downloaded_rows(self) -> None:
        for item in self.downloaded_tree.get_children():
            self.downloaded_tree.delete(item)

        rows = list(self.download_rows_cache)
        rows.sort(key=lambda r: str(r[0] or ""), reverse=self.download_date_sort_desc)

        selected_keywords = set(self.get_selected_keywords())
        if selected_keywords:
            rows = [r for r in rows if selected_keywords.intersection(set(_split_keywords(r[6])))]

        for row in rows:
            self.downloaded_tree.insert("", tk.END, values=row)
        self._refresh_summary_link_labels()

    def _on_tree_scrolled(self, scrollbar: ttk.Scrollbar, first: str, last: str) -> None:
        scrollbar.set(first, last)
        self.root.after_idle(self._refresh_summary_link_labels)

    def _render_keyword_listbox(self) -> None:
        if not hasattr(self, "download_keyword_listbox"):
            return
        query = self.keyword_search_var.get().strip().lower()
        if query:
            shown = [kw for kw in self.download_keyword_all if query in kw.lower()]
        else:
            shown = list(self.download_keyword_all)
        self.download_keyword_listbox.delete(0, tk.END)
        for kw in shown:
            self.download_keyword_listbox.insert(tk.END, kw)
        for i, kw in enumerate(shown):
            if kw in self.download_keyword_selected:
                self.download_keyword_listbox.selection_set(i)

    def on_keyword_search_change(self) -> None:
        self._render_keyword_listbox()

    def on_keyword_listbox_select(self, _event: tk.Event) -> None:
        visible_keywords = [self.download_keyword_listbox.get(i) for i in range(self.download_keyword_listbox.size())]
        visible_selected = {self.download_keyword_listbox.get(i) for i in self.download_keyword_listbox.curselection()}
        for kw in visible_keywords:
            if kw in self.download_keyword_selected and kw not in visible_selected:
                self.download_keyword_selected.remove(kw)
        self.download_keyword_selected.update(visible_selected)
        self._render_downloaded_rows()

    def _on_summary_link_click(self, doi: str, item_id: str) -> None:
        if not doi:
            messagebox.showwarning("提示", "该记录没有 DOI，无法查看总结")
            return
        self.downloaded_tree.selection_set(item_id)
        self._render_summary_for_selected([doi])

    def _refresh_summary_link_labels(self) -> None:
        if not hasattr(self, "downloaded_tree"):
            return
        active_items: set[str] = set()
        for item in self.downloaded_tree.get_children():
            vals = self.downloaded_tree.item(item, "values")
            if len(vals) < 6 or str(vals[5]).strip() != "查看":
                continue
            bbox = self.downloaded_tree.bbox(item, "summary_status")
            if not bbox:
                continue
            x, y, w, h = bbox
            doi = str(vals[3] if len(vals) >= 4 else "").strip()
            active_items.add(item)
            lbl = self.summary_link_labels.get(item)
            if lbl is None:
                lbl = tk.Label(
                    self.downloaded_tree,
                    text="查看",
                    fg="#2563eb",
                    bg="#ffffff",
                    cursor="hand2",
                    font=self.summary_link_font,
                )
                self.summary_link_labels[item] = lbl
            else:
                lbl.configure(bg="#ffffff")
            lbl.bind("<Button-1>", lambda _e, d=doi, iid=item: self._on_summary_link_click(d, iid))
            lbl.place(x=x + 1, y=y + 1, width=max(w - 2, 1), height=max(h - 2, 1))
        for item_id in list(self.summary_link_labels.keys()):
            if item_id not in active_items:
                self.summary_link_labels[item_id].destroy()
                self.summary_link_labels.pop(item_id, None)

    def get_selected_keywords(self) -> list[str]:
        return sorted(self.download_keyword_selected)

    def clear_keyword_filter(self) -> None:
        self.download_keyword_selected.clear()
        self.keyword_search_var.set("")
        if hasattr(self, "download_keyword_listbox"):
            self.download_keyword_listbox.selection_clear(0, tk.END)
            self._render_keyword_listbox()
        self._render_downloaded_rows()

    def sort_downloaded_by_date(self) -> None:
        self.download_date_sort_desc = not self.download_date_sort_desc
        self._render_downloaded_rows()

    def on_view_selected_summary(self) -> None:
        selected = self.downloaded_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择要查看总结的文献")
            return
        selected_dois: list[str] = []
        for item in selected:
            vals = self.downloaded_tree.item(item, "values")
            doi = (vals[3] if len(vals) >= 4 else "")
            doi = str(doi).strip()
            if doi:
                selected_dois.append(doi)
        if not selected_dois:
            messagebox.showwarning("提示", "选中的记录没有 DOI")
            return
        self._render_summary_for_selected(selected_dois)

    def on_downloaded_tree_click(self, event: tk.Event) -> None:
        region = self.downloaded_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        column = self.downloaded_tree.identify_column(event.x)
        item = self.downloaded_tree.identify_row(event.y)
        if column != "#6" or not item:
            return

        vals = self.downloaded_tree.item(item, "values")
        if len(vals) < 6 or str(vals[5]).strip() != "查看":
            return

        doi = str(vals[3] if len(vals) >= 4 else "").strip()
        if not doi:
            messagebox.showwarning("提示", "该记录没有 DOI，无法查看总结")
            return
        self.downloaded_tree.selection_set(item)
        self._render_summary_for_selected([doi])

    def on_downloaded_tree_motion(self, event: tk.Event) -> None:
        region = self.downloaded_tree.identify("region", event.x, event.y)
        if region != "cell":
            self.downloaded_tree.configure(cursor="")
            return
        column = self.downloaded_tree.identify_column(event.x)
        item = self.downloaded_tree.identify_row(event.y)
        if column != "#6" or not item:
            self.downloaded_tree.configure(cursor="")
            return
        vals = self.downloaded_tree.item(item, "values")
        if len(vals) >= 6 and str(vals[5]).strip() == "查看":
            self.downloaded_tree.configure(cursor="hand2")
            return
        self.downloaded_tree.configure(cursor="")

    def on_downloaded_tree_leave(self, _event: tk.Event) -> None:
        self.downloaded_tree.configure(cursor="")

    def on_add_journal(self) -> None:
        name = self.journal_name.get().strip()
        if not name:
            messagebox.showerror("输入错误", "请填写期刊名称")
            return
        _append_journal(
            name=name,
            publisher=self.journal_publisher.get(),
            issn_print=self.journal_issn_print.get(),
            issn_online=self.journal_issn_online.get(),
        )
        self.refresh_journal_table()
        self.log(f"• 已添加期刊：{name}")

    def on_delete_journal(self) -> None:
        selected = self.journal_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先在表格里选中一行")
            return
        idx = int(selected[0])
        title = self.journal_tree.item(selected[0], "values")[0]
        _delete_journal(idx)
        self.refresh_journal_table()
        self.log(f"• 已删除期刊：{title}")

    def open_api_link(self, url: str) -> None:
        try:
            webbrowser.open_new(url)
            self.log(f"• 已打开链接：{url}")
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开链接：{e}")

    def open_calendar(self, target_var: tk.StringVar) -> None:
        popup = tk.Toplevel(self.root)
        popup.configure(bg=BG_PANEL)
        popup.title("选择日期")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()

        try:
            cur = date.fromisoformat(target_var.get().strip())
        except Exception:
            cur = date.today()

        self._calendar_state = {"popup": popup, "target": target_var, "year": cur.year, "month": cur.month}
        self._render_calendar()

        # 让日历弹窗出现在鼠标附近，而不是默认左上角
        popup.update_idletasks()
        width = popup.winfo_reqwidth()
        height = popup.winfo_reqheight()

        x = self.root.winfo_pointerx() + 12
        y = self.root.winfo_pointery() + 12

        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        x = max(0, min(x, screen_w - width))
        y = max(0, min(y, screen_h - height))
        popup.geometry(f"+{x}+{y}")

    def _render_calendar(self) -> None:
        popup = self._calendar_state["popup"]
        for w in popup.winfo_children():
            w.destroy()

        year = self._calendar_state["year"]
        month = self._calendar_state["month"]

        header = ttk.Frame(popup, padding=8)
        header.pack(fill=tk.X)
        ttk.Button(header, text="<", width=3, command=lambda: self._move_month(-1)).pack(side=tk.LEFT)
        ttk.Label(header, text=f"{year}-{month:02d}", font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=10)
        ttk.Button(header, text=">", width=3, command=lambda: self._move_month(1)).pack(side=tk.LEFT)

        grid = ttk.Frame(popup, padding=(8, 0, 8, 8))
        grid.pack()
        for i, n in enumerate(["一", "二", "三", "四", "五", "六", "日"]):
            ttk.Label(grid, text=n, width=4, anchor=tk.CENTER).grid(row=0, column=i, padx=1, pady=1)

        for r, week in enumerate(calendar.monthcalendar(year, month), start=1):
            for c, d in enumerate(week):
                if d == 0:
                    ttk.Label(grid, text="", width=4).grid(row=r, column=c, padx=1, pady=1)
                else:
                    ttk.Button(grid, text=str(d), width=4, command=lambda day=d: self._select_date(day)).grid(row=r, column=c, padx=1, pady=1)

    def _move_month(self, delta: int) -> None:
        y = self._calendar_state["year"]
        m = self._calendar_state["month"] + delta
        if m == 0:
            y -= 1
            m = 12
        elif m == 13:
            y += 1
            m = 1
        self._calendar_state["year"] = y
        self._calendar_state["month"] = m
        self._render_calendar()

    def _select_date(self, day: int) -> None:
        y = self._calendar_state["year"]
        m = self._calendar_state["month"]
        self._calendar_state["target"].set(date(y, m, day).isoformat())
        self._calendar_state["popup"].destroy()

    def on_save_provider_keys(self) -> None:
        _save_provider_api_keys(
            elsevier_key=self.elsevier_key.get(),
            wiley_key=self.wiley_key.get(),
            springer_key=self.springer_key.get(),
            ieee_key=self.ieee_key.get(),
        )
        self.log(f"• API Key 已保存到 {SECRETS_PATH}")
        messagebox.showinfo("成功", "已保存")

    def on_save_summary_config(self, show_success: bool = True) -> bool:
        max_tokens = self.summary_max_tokens.get().strip()
        if max_tokens and not max_tokens.isdigit():
            messagebox.showerror("输入错误", "最大输出 token 必须是整数")
            return False

        provider = self.summary_provider.get().strip()
        if provider not in SUMMARY_API_PROVIDERS:
            messagebox.showerror("输入错误", "请选择有效的 API 提供商")
            return False

        api_key = self.summary_api_key.get().strip()
        if not api_key:
            messagebox.showerror("输入错误", "API Key 不能为空，否则会报 No API-key provided")
            return False

        _save_summary_llm_config(
            provider=provider,
            base_url=self.summary_base_url.get(),
            api_key=api_key,
            max_tokens=max_tokens,
        )
        if show_success:
            messagebox.showinfo("成功", "文献总结配置已保存")
        return True

    def on_summary_provider_change(self) -> None:
        selected = self.summary_provider.get()
        if selected not in SUMMARY_API_PROVIDERS:
            return
        base_url, api_key = _get_saved_provider_fields(selected)
        self.summary_base_url.set(base_url)
        self.summary_api_key.set(api_key)

    def _append_summary_output(self, text: str) -> None:
        self.summary_output.insert(tk.END, text + "\n")
        self.summary_output.see(tk.END)

    def _render_summary_for_selected(self, selected_dois: list[str]) -> None:
        data = _load_summaries_for_dois(selected_dois)
        self.summary_output.delete("1.0", tk.END)
        if not data:
            self._append_summary_output("未查询到所选文献的总结结果。")
            return
        for doi in selected_dois:
            d = data.get(str(doi).strip()) or data.get(_normalize_doi(doi))
            if not d:
                self._append_summary_output(f"DOI: {doi}\n状态: 未总结\n")
                continue
            status_text = str(d.get("status", "") or "")
            error_text = str(d.get("error", "") or "")
            detail = (
                f"DOI: {doi}\n"
                f"状态: {status_text}\n"
                f"模型: {d.get('model','')}\n"
                f"总结时间: {d.get('summarized_at','')}\n"
                f"方法总结:\n{d.get('method_summary','')}\n\n"
                f"结果总结:\n{d.get('result_summary','')}\n"
            )
            if error_text.strip() and status_text.lower() != "ok":
                detail += f"错误: {error_text}\n"
            self._append_summary_output(detail + "-" * 80)

    def _run_summarize_thread(self, selected_dois: list[str]) -> None:
        parse_result: subprocess.CompletedProcess[str]
        summarize_result: subprocess.CompletedProcess[str]
        try:
            parse_cmd = [sys.executable, str(BASE_DIR / "app" / "parse_fulltexts.py")]
            print(f"[GUI][summary] running parser command={parse_cmd}")
            parse_result = subprocess.run(
                parse_cmd,
                cwd=BASE_DIR,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            print(f"[GUI][summary] parse returncode={parse_result.returncode}")
            print("[GUI][summary] stage=parse_done_start_summarize")

            doi_arg = ",".join(selected_dois)
            summarize_cmd = [sys.executable, str(BASE_DIR / "app" / "summarize_papers.py"), "--dois", doi_arg]
            print(f"[GUI][summary] running summarize command={summarize_cmd}")
            summarize_result = subprocess.run(
                summarize_cmd,
                cwd=BASE_DIR,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            print(f"[GUI][summary] summarize returncode={summarize_result.returncode}")
            print("[GUI][summary] stage=summarize_done_render")
        except Exception as e:
            parse_result = subprocess.CompletedProcess(args=["parse_fulltexts.py"], returncode=1, stdout="", stderr=str(e))
            summarize_result = subprocess.CompletedProcess(args=["summarize_papers.py"], returncode=1, stdout="", stderr=str(e))
            print(f"[GUI][summary] summarize flow exception={e!r}")

        def _done() -> None:
            self.summary_analyze_btn.config(state=tk.NORMAL)
            self.summary_output.delete("1.0", tk.END)

            parsed_count = "未知"
            m = re.search(r"parsed_success_count:\s*(\d+)", parse_result.stdout or "")
            if m:
                parsed_count = m.group(1)
            self._append_summary_output(f"解析完成：成功解析 {parsed_count} 篇文献")

            self._append_summary_output("[parse_fulltexts.py STDOUT]")
            self._append_summary_output(parse_result.stdout or "(empty)")
            self._append_summary_output("\n[parse_fulltexts.py STDERR]")
            self._append_summary_output(parse_result.stderr or "(empty)")
            self._append_summary_output("\n[summarize_papers.py STDOUT]")
            self._append_summary_output(summarize_result.stdout or "(empty)")
            self._append_summary_output("\n[summarize_papers.py STDERR]")
            self._append_summary_output(summarize_result.stderr or "(empty)")
            self._append_summary_output("\n[所选文献总结结果]")
            self._render_summary_for_selected(selected_dois)

        self.root.after(0, _done)

    def on_analyze_selected(self) -> None:
        selected = self.downloaded_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择要总结的文献（支持单选/多选）")
            return

        selected_dois: list[str] = []
        for item in selected:
            vals = self.downloaded_tree.item(item, "values")
            doi = (vals[3] if len(vals) >= 4 else "")
            doi = str(doi).strip()
            if doi:
                selected_dois.append(doi)

        if not selected_dois:
            messagebox.showwarning("提示", "选中的记录没有 DOI，无法总结")
            return

        print(f"[GUI][summary] analyze selected_dois={selected_dois}")
        print("[GUI][summary] stage=save_config_before_analyze")
        # 分析前强制使用当前页面配置，避免“只填了源地址但没保存 API Key”导致无 key 报错
        if not self.on_save_summary_config(show_success=False):
            return

        self.summary_analyze_btn.config(state=tk.DISABLED)
        self.summary_output.delete("1.0", tk.END)
        self._append_summary_output(f"开始智能分析，共 {len(selected_dois)} 篇...\n")
        print("[GUI][summary] stage=thread_start")
        threading.Thread(target=self._run_summarize_thread, args=(selected_dois,), daemon=True).start()

    def _handle_run_output_line(self, line: str) -> None:
        line = (line or "").rstrip("\n")
        if not line:
            return
        self.log(line)

        m_total = re.search(r"\[DL\s+(\d+)/(\d+)\]", line)
        if m_total:
            self.download_total_expected = max(int(m_total.group(2)), 1)

        # 本地实际下载成功（不计 already ok）
        if "already ok" not in line and re.search(r"->\s+(?:springer\s+|ieee\s+)?(ok|success|downloaded)\b", line):
            self.download_success_count += 1

        # Wiley 批量下载汇总（ok=x/y）
        m_wiley = re.search(r"\[Wiley tdm-client\]\s+ok=(\d+)/(\d+)", line)
        if m_wiley:
            self.download_success_count += int(m_wiley.group(1))

        total = self.download_total_expected
        success = self.download_success_count
        if total > 0:
            # 以“成功下载数/总待下载数”作为真实进度
            pct = min(95, int(8 + (min(success, total) / total) * 87))
            self.progress_var.set(pct)
            self.progress_label.config(text=f"下载进度 成功 {success}/{total}（{pct}%）")
            return

        m_done = re.search(r"Done\. New articles:\s*(\d+)", line)
        if m_done:
            self.progress_var.set(98)
            self.progress_label.config(text="下载进度 完成发现/下载（98%）")

    def _run_daily_with_progress(self) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable, str(BASE_DIR / "app" / "run_daily.py")]
        proc = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            self.root.after(0, lambda l=line: self._handle_run_output_line(l))
        returncode = proc.wait()
        return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout="".join(lines), stderr="")

    def _finish_run(self, result: subprocess.CompletedProcess[str]) -> None:
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.progress_var.set(100 if result.returncode == 0 else 0)
        self.progress_label.config(text=f"总进度 {self.progress_var.get()}%")
        self.log("\n[STDOUT]")
        self.log(result.stdout or "(empty)")
        self.log("\n[STDERR]")
        self.log(result.stderr or "(empty)")
        if result.returncode == 0:
            messagebox.showinfo("完成", "下载完成")
            self.refresh_downloaded_articles_table()
        else:
            messagebox.showerror("失败", f"run_daily.py 失败，返回码={result.returncode}")

    def _run_task_thread(self, date_from: str, date_until: str) -> None:
        try:
            _set_date_range(date_from=date_from, date_until=date_until)
            result = self._run_daily_with_progress()
        except Exception as e:
            result = subprocess.CompletedProcess(args=["run_daily.py"], returncode=1, stdout="", stderr=str(e))
        self.root.after(0, lambda: self._finish_run(result))

    def on_run_download(self) -> None:
        if self.running:
            return
        date_from = self.date_from.get().strip()
        date_until = self.date_until.get().strip()
        if not date_from or not date_until:
            messagebox.showerror("输入错误", "请填写开始和结束时间（YYYY-MM-DD）")
            return

        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.clear_logs()
        self.log(f"• 任务启动：{date_from} ~ {date_until}")
        self.download_total_expected = 0
        self.download_success_count = 0
        self.progress_var.set(5)
        self.progress_label.config(text="下载进度 成功 0/0（5%）")
        threading.Thread(target=self._run_task_thread, args=(date_from, date_until), daemon=True).start()


def main() -> None:
    root = tk.Tk()
    PaperBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
