from __future__ import annotations

import calendar
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from datetime import date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import yaml
from app.gui_style import apply_theme, BG_MAIN, BG_PANEL, BORDER, TEXT_MAIN

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config" / "config.yml"
SECRETS_PATH = BASE_DIR / "config" / "secrets.yml"
PUBLISHERS = ["elsevier", "wiley", "springer", "ieee", "other"]
SUMMARY_API_PROVIDERS = {
    # UI选项: (llm.provider, api_key_env, secret_key, 默认base_url)
    "chatgpt": ("chatgpt", "OPENAI_API_KEY", "openai_api_key", "https://api.openai.com/v1"),
    "gemini": ("gemini", "GEMINI_API_KEY", "gemini_api_key", ""),
    "claude": ("claude", "ANTHROPIC_API_KEY", "anthropic_api_key", ""),
    "千问": ("qwen", "DASHSCOPE_API_KEY", "dashscope_api_key", "https://dashscope.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1"),
    "元宝": ("yuanbao", "YUANBAO_API_KEY", "yuanbao_api_key", ""),
    "deepseek": ("deepseek", "DEEPSEEK_API_KEY", "deepseek_api_key", "https://api.deepseek.com/v1"),
    "智谱": ("zhipu", "ZHIPU_API_KEY", "zhipu_api_key", "https://open.bigmodel.cn/api/paas/v4"),
    "custom": ("custom", "CUSTOM_LLM_API_KEY", "custom_llm_api_key", ""),
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


def _append_journal(name: str, short_name: str, publisher: str, issn_print: str, issn_online: str) -> None:
    cfg = _load_yaml(CONFIG_PATH)
    journals = cfg.setdefault("journals", [])
    journal = {"name": name.strip(), "publisher": publisher.strip().lower()}
    if short_name.strip():
        journal["short_name"] = short_name.strip()
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
    selected = provider if provider in SUMMARY_API_PROVIDERS else "custom"
    llm_provider, env_name, secret_key, default_base_url = SUMMARY_API_PROVIDERS[selected]

    llm["provider"] = llm_provider
    llm["base_url"] = (base_url or "").strip() or default_base_url
    llm["api_key_env"] = env_name
    if max_tokens.strip():
        llm["max_output_tokens"] = int(max_tokens.strip())
    _save_yaml(CONFIG_PATH, cfg)

    secrets = _load_yaml(SECRETS_PATH)
    if api_key.strip():
        secrets[secret_key] = api_key.strip()
    _save_yaml(SECRETS_PATH, secrets)




def _load_saved_gui_settings() -> dict:
    cfg = _load_yaml(CONFIG_PATH)
    sec = _load_yaml(SECRETS_PATH)
    llm = cfg.get("llm") or {}
    raw_provider = str(llm.get("provider") or "custom").strip().lower()
    ui_provider = PROVIDER_TO_UI.get(raw_provider, "custom")
    llm_provider, env_name, secret_key, _default_base_url = SUMMARY_API_PROVIDERS.get(ui_provider, SUMMARY_API_PROVIDERS["custom"])
    return {
        "elsevier_api_key": sec.get("elsevier_api_key", ""),
        "wiley_tdm_client_token": sec.get("wiley_tdm_client_token", ""),
        "springer_api_key": sec.get("springer_api_key", ""),
        "ieee_api_key": sec.get("ieee_api_key", ""),
        "summary_base_url": llm.get("base_url", ""),
        "summary_max_tokens": str(llm.get("max_output_tokens", "") or ""),
        "summary_provider": ui_provider,
        "summary_api_key": sec.get(secret_key, sec.get("custom_llm_api_key", "")),
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


def _load_downloaded_articles(limit: int = 300) -> list[tuple[str, str, str, str, str]]:
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
                  COALESCE(f.status, '')
                FROM fulltexts f
                LEFT JOIN articles a ON a.doi = f.doi
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
                  COALESCE(f.status, '')
                FROM fulltexts f
                LEFT JOIN articles a ON a.doi = f.doi
                ORDER BY COALESCE(f.downloaded_at, '') DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [(str(r[0] or ""), str(r[1] or ""), str(r[2] or ""), str(r[3] or ""), str(r[4] or "")) for r in rows]
    finally:
        conn.close()


class PaperBotGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("论文库下载工具")
        self.root.geometry("1320x840")
        self.root.minsize(1160, 720)

        self.running = False
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
        top.pack(fill=tk.BOTH, expand=True)

        cols = ("published", "title", "journal", "doi", "status")
        self.downloaded_tree = ttk.Treeview(top, columns=cols, show="headings", height=14)
        self.downloaded_tree.heading("published", text="日期")
        self.downloaded_tree.heading("title", text="标题")
        self.downloaded_tree.heading("journal", text="期刊")
        self.downloaded_tree.heading("doi", text="DOI")
        self.downloaded_tree.heading("status", text="下载状态")
        self.downloaded_tree.column("published", width=90, anchor=tk.CENTER)
        self.downloaded_tree.column("title", width=330)
        self.downloaded_tree.column("journal", width=180)
        self.downloaded_tree.column("doi", width=200)
        self.downloaded_tree.column("status", width=90, anchor=tk.CENTER)

        ybar = ttk.Scrollbar(top, orient=tk.VERTICAL, command=self.downloaded_tree.yview)
        self.downloaded_tree.configure(yscrollcommand=ybar.set)
        self.downloaded_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ybar.pack(side=tk.LEFT, fill=tk.Y)

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

    def _build_journal_panel(self, parent: ttk.LabelFrame) -> None:
        form = ttk.Frame(parent)
        form.pack(fill=tk.X)

        self.journal_name = tk.StringVar()
        self.journal_short = tk.StringVar()
        self.journal_publisher = tk.StringVar(value="elsevier")
        self.journal_issn_print = tk.StringVar()
        self.journal_issn_online = tk.StringVar()

        ttk.Label(form, text="期刊名称").grid(row=0, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_name, width=42).grid(row=0, column=1, sticky=tk.EW, padx=8, pady=6)
        ttk.Label(form, text="期刊缩写").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_short, width=42).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=6)
        ttk.Label(form, text="出版社").grid(row=2, column=0, sticky=tk.W, pady=6)
        ttk.Combobox(form, textvariable=self.journal_publisher, values=PUBLISHERS, state="readonly", width=39).grid(row=2, column=1, sticky=tk.EW, padx=8, pady=6)
        ttk.Label(form, text="ISSN (print，可选)").grid(row=3, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_issn_print, width=42).grid(row=3, column=1, sticky=tk.EW, padx=8, pady=6)
        ttk.Label(form, text="ISSN (online，可选)").grid(row=4, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_issn_online, width=42).grid(row=4, column=1, sticky=tk.EW, padx=8, pady=6)
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
        for item in self.downloaded_tree.get_children():
            self.downloaded_tree.delete(item)
        try:
            rows = _load_downloaded_articles()
        except Exception as e:
            self.log(f"• 读取文献列表失败：{e}")
            rows = []
        for row in rows:
            self.downloaded_tree.insert("", tk.END, values=row)

    def on_add_journal(self) -> None:
        name = self.journal_name.get().strip()
        if not name:
            messagebox.showerror("输入错误", "请填写期刊名称")
            return
        _append_journal(
            name=name,
            short_name=self.journal_short.get(),
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

    def on_save_summary_config(self) -> None:
        max_tokens = self.summary_max_tokens.get().strip()
        if max_tokens and not max_tokens.isdigit():
            messagebox.showerror("输入错误", "最大输出 token 必须是整数")
            return
        _save_summary_llm_config(
            provider=self.summary_provider.get(),
            base_url=self.summary_base_url.get(),
            api_key=self.summary_api_key.get(),
            max_tokens=max_tokens,
        )
        messagebox.showinfo("成功", "文献总结配置已保存")

    def on_summary_provider_change(self) -> None:
        selected = self.summary_provider.get()
        if selected not in SUMMARY_API_PROVIDERS:
            return
        _llm_provider, _env, _secret, default_base_url = SUMMARY_API_PROVIDERS[selected]
        if default_base_url and not self.summary_base_url.get().strip():
            self.summary_base_url.set(default_base_url)

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
            result = _run_daily()
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
        self.progress_var.set(35)
        self.progress_label.config(text="总进度 35%")
        threading.Thread(target=self._run_task_thread, args=(date_from, date_until), daemon=True).start()


def main() -> None:
    root = tk.Tk()
    PaperBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
