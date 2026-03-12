from __future__ import annotations

import subprocess
import sys
import threading
import webbrowser
import calendar
from datetime import date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config" / "config.yml"
SECRETS_PATH = BASE_DIR / "config" / "secrets.yml"
PUBLISHERS = ["elsevier", "wiley", "springer", "ieee", "other"]
UNIFIED_BG = "#f2f3f5"


def _date_options(days_back: int = 3650, days_forward: int = 365) -> list[str]:
    today = date.today()
    start = today - timedelta(days=days_back)
    end = today + timedelta(days=days_forward)

    values: list[str] = []
    cur = start
    while cur <= end:
        values.append(cur.isoformat())
        cur += timedelta(days=1)
    return values


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def _save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _append_journal(name: str, short_name: str, publisher: str, issn: str) -> None:
    cfg = _load_yaml(CONFIG_PATH)
    journals = cfg.setdefault("journals", [])

    journal = {
        "name": name.strip(),
        "publisher": publisher.strip().lower(),
    }
    if short_name.strip():
        journal["short_name"] = short_name.strip()
    if issn.strip():
        journal["crossref_issn"] = issn.strip()

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


def _save_api_keys(elsevier_key: str, wiley_key: str, springer_key: str, ieee_key: str) -> None:
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
        capture_output=True,
        check=False,
    )


class PaperBotGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("论文库下载工具")
        self.root.geometry("1280x820")
        self.root.minsize(1100, 700)

        self.running = False
        self._build_styles()
        self._build_layout()
        self.refresh_journal_table()

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("Sidebar.TFrame", background=UNIFIED_BG)
        style.configure("Main.TFrame", background=UNIFIED_BG)
        style.configure("Card.TLabelframe", background="#ffffff")
        style.configure("Card.TLabelframe.Label", background="#ffffff", font=("Microsoft YaHei", 12, "bold"))
        style.configure("Header.TLabel", background=UNIFIED_BG, font=("Microsoft YaHei", 19, "bold"), foreground="#0f172a")
        style.configure("SubHeader.TLabel", background=UNIFIED_BG, font=("Microsoft YaHei", 18, "bold"), foreground="#111827")
        style.configure("Menu.TButton", font=("Microsoft YaHei", 13), padding=(12, 8))
        style.configure("MenuActive.TButton", font=("Microsoft YaHei", 13, "bold"), padding=(12, 8), foreground="#1d4ed8")
        style.configure("Primary.TButton", font=("Microsoft YaHei", 13, "bold"), padding=(16, 10))
        style.configure("Success.TButton", font=("Microsoft YaHei", 13, "bold"), padding=(14, 8))

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root)
        shell.pack(fill=tk.BOTH, expand=True)

        self.sidebar = ttk.Frame(shell, width=290, style="Sidebar.TFrame")
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        self.main = ttk.Frame(shell, style="Main.TFrame")
        self.main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self) -> None:
        ttk.Label(
            self.sidebar,
            text="论文库下载工具",
            background=UNIFIED_BG,
            font=("Microsoft YaHei", 20, "bold"),
        ).pack(anchor=tk.W, padx=26, pady=(28, 2))
        ttk.Label(
            self.sidebar,
            text="Paper Downloader",
            background=UNIFIED_BG,
            foreground="#64748b",
            font=("Microsoft YaHei", 13),
        ).pack(anchor=tk.W, padx=26, pady=(0, 24))

        ttk.Button(self.sidebar, text="📘  期刊配置", style="MenuActive.TButton").pack(fill=tk.X, padx=18, pady=6)
        ttk.Button(self.sidebar, text="🔑  API Key", style="Menu.TButton").pack(fill=tk.X, padx=18, pady=6)
        ttk.Button(self.sidebar, text="⬇️  下载任务", style="Menu.TButton").pack(fill=tk.X, padx=18, pady=6)
        ttk.Button(self.sidebar, text="⚙️  系统设置", style="Menu.TButton").pack(fill=tk.X, padx=18, pady=6)

        ttk.Label(self.sidebar, text="Version 1.0", background=UNIFIED_BG, foreground="#64748b", font=("Microsoft YaHei", 12)).pack(side=tk.BOTTOM, anchor=tk.W, padx=26, pady=20)

    def _build_main(self) -> None:
        top_wrap = ttk.Frame(self.main, style="Main.TFrame")
        top_wrap.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        upper = ttk.Frame(top_wrap, style="Main.TFrame")
        upper.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(upper, text="期刊信息", padding=14, style="Card.TLabelframe")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        right = ttk.LabelFrame(upper, text="text and data mining API key管理", padding=14, style="Card.TLabelframe")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        self._build_journal_panel(left)
        self._build_api_panel(right)

        bottom = ttk.LabelFrame(top_wrap, text="下载任务", padding=14, style="Card.TLabelframe")
        bottom.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        self._build_download_panel(bottom)

    def _build_journal_panel(self, parent: ttk.LabelFrame) -> None:
        form = ttk.Frame(parent)
        form.pack(fill=tk.X)

        self.journal_name = tk.StringVar()
        self.journal_short = tk.StringVar()
        self.journal_publisher = tk.StringVar(value="elsevier")
        self.journal_issn = tk.StringVar()

        ttk.Label(form, text="期刊名称").grid(row=0, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_name, width=42).grid(row=0, column=1, sticky=tk.EW, padx=8, pady=6)

        ttk.Label(form, text="期刊缩写").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_short, width=42).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=6)

        ttk.Label(form, text="出版社").grid(row=2, column=0, sticky=tk.W, pady=6)
        ttk.Combobox(form, textvariable=self.journal_publisher, values=PUBLISHERS, state="readonly", width=39).grid(row=2, column=1, sticky=tk.EW, padx=8, pady=6)

        ttk.Label(form, text="ISSN (可选)").grid(row=3, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.journal_issn, width=42).grid(row=3, column=1, sticky=tk.EW, padx=8, pady=6)

        form.columnconfigure(1, weight=1)

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(8, 10))
        ttk.Button(btn_row, text="＋ 添加", command=self.on_add_journal, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(btn_row, text="删除选中", command=self.on_delete_journal).pack(side=tk.LEFT, padx=8)

        ttk.Label(parent, text="已添加期刊", font=("Microsoft YaHei", 13, "bold")).pack(anchor=tk.W, pady=(4, 6))

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

    def _build_api_panel(self, parent: ttk.LabelFrame) -> None:
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

        for i, (title, var, url) in enumerate(rows):
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=8)
            title_row = tk.Frame(row, bg=UNIFIED_BG)
            title_row.pack(fill=tk.X)
            tk.Label(title_row, text=f"{title}", font=("Microsoft YaHei", 12, "bold"), bg=UNIFIED_BG).pack(side=tk.LEFT)
            link = tk.Label(
                title_row,
                text=f"点我获取{title}",
                fg="#2563eb",
                cursor="hand2",
                font=("Microsoft YaHei", 10, "underline"),
                bg=UNIFIED_BG,
            )
            link.pack(side=tk.LEFT, padx=(10, 0))
            link.bind("<Button-1>", lambda _e, u=url: self.open_api_link(u))
            entry_row = ttk.Frame(row)
            entry_row.pack(fill=tk.X, pady=(2, 0))
            ttk.Entry(entry_row, textvariable=var, show="*", width=42).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Label(entry_row, text="✅", foreground="#10b981", font=("Microsoft YaHei", 14)).pack(side=tk.LEFT, padx=8)

        ttk.Button(parent, text="✔ 保存", command=self.on_save_keys, style="Success.TButton").pack(anchor=tk.E, pady=(18, 0))

    def _build_download_panel(self, parent: ttk.LabelFrame) -> None:
        grid = ttk.Frame(parent)
        grid.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(grid)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))

        ttk.Label(left, text="开始时间", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W)
        self.date_from = tk.StringVar(value=(date.today() - timedelta(days=30)).isoformat())
        from_row = ttk.Frame(left)
        from_row.pack(anchor=tk.W, pady=(6, 12))
        ttk.Entry(from_row, textvariable=self.date_from, width=22, state="readonly").pack(side=tk.LEFT)
        ttk.Button(from_row, text="📅", width=3, command=lambda: self.open_calendar(self.date_from)).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(left, text="结束时间", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W)
        self.date_until = tk.StringVar(value=date.today().isoformat())
        until_row = ttk.Frame(left)
        until_row.pack(anchor=tk.W, pady=(6, 12))
        ttk.Entry(until_row, textvariable=self.date_until, width=22, state="readonly").pack(side=tk.LEFT)
        ttk.Button(until_row, text="📅", width=3, command=lambda: self.open_calendar(self.date_until)).pack(side=tk.LEFT, padx=(6, 0))

        btns = ttk.Frame(left)
        btns.pack(anchor=tk.W, pady=(6, 4))
        self.start_btn = ttk.Button(btns, text="⬇ 开始下载", command=self.on_run, style="Primary.TButton")
        self.start_btn.pack(side=tk.LEFT)
        ttk.Button(btns, text="■ 清空日志", command=self.clear_logs).pack(side=tk.LEFT, padx=8)

        right = ttk.Frame(grid)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(right, text="任务日志", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W)
        self.output_box = tk.Text(right, height=11, wrap="word", font=("Consolas", 11))
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

        journals = _get_journals()
        for idx, j in enumerate(journals):
            name = j.get("name", "")
            pub = (j.get("publisher") or "").capitalize()
            issn = j.get("crossref_issn") or j.get("issn_print") or j.get("issn_online") or ""
            self.journal_tree.insert("", tk.END, iid=str(idx), values=(name, pub, issn))

    def on_add_journal(self) -> None:
        name = self.journal_name.get().strip()
        if not name:
            messagebox.showerror("输入错误", "请填写期刊名称")
            return

        _append_journal(
            name=name,
            short_name=self.journal_short.get(),
            publisher=self.journal_publisher.get(),
            issn=self.journal_issn.get(),
        )
        self.refresh_journal_table()
        self.log(f"• 已添加期刊：{name}")

    def on_delete_journal(self) -> None:
        selected = self.journal_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先在表格里选中一行")
            return

        idx = int(selected[0])
        values = self.journal_tree.item(selected[0], "values")
        _delete_journal(idx)
        self.refresh_journal_table()
        self.log(f"• 已删除期刊：{values[0] if values else idx}")

    def open_api_link(self, url: str) -> None:
        try:
            webbrowser.open_new(url)
            self.log(f"• 已打开链接：{url}")
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开链接：{e}")

    def open_calendar(self, target_var: tk.StringVar) -> None:
        popup = tk.Toplevel(self.root)
        popup.title("选择日期")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()

        try:
            cur = date.fromisoformat(target_var.get().strip())
        except Exception:
            cur = date.today()

        self._calendar_state = {
            "popup": popup,
            "target": target_var,
            "year": cur.year,
            "month": cur.month,
        }
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
        ttk.Label(header, text=f"{year}-{month:02d}", font=("Microsoft YaHei", 12, "bold")).pack(side=tk.LEFT, padx=10)
        ttk.Button(header, text=">", width=3, command=lambda: self._move_month(1)).pack(side=tk.LEFT)

        grid = ttk.Frame(popup, padding=(8, 0, 8, 8))
        grid.pack()

        week_names = ["一", "二", "三", "四", "五", "六", "日"]
        for i, n in enumerate(week_names):
            ttk.Label(grid, text=n, width=4, anchor=tk.CENTER).grid(row=0, column=i, padx=1, pady=1)

        month_data = calendar.monthcalendar(year, month)
        for r, week in enumerate(month_data, start=1):
            for c, d in enumerate(week):
                if d == 0:
                    ttk.Label(grid, text="", width=4).grid(row=r, column=c, padx=1, pady=1)
                else:
                    ttk.Button(
                        grid,
                        text=str(d),
                        width=4,
                        command=lambda day=d: self._select_date(day),
                    ).grid(row=r, column=c, padx=1, pady=1)

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

    def on_save_keys(self) -> None:
        _save_api_keys(
            elsevier_key=self.elsevier_key.get(),
            wiley_key=self.wiley_key.get(),
            springer_key=self.springer_key.get(),
            ieee_key=self.ieee_key.get(),
        )
        self.log(f"• API Key 已保存到 {SECRETS_PATH}")
        messagebox.showinfo("成功", "已保存到 secret.yml")

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
        else:
            messagebox.showerror("失败", f"run_daily.py 失败，返回码={result.returncode}")

    def _run_task_thread(self, date_from: str, date_until: str) -> None:
        try:
            _set_date_range(date_from=date_from, date_until=date_until)
            result = _run_daily()
        except Exception as e:
            result = subprocess.CompletedProcess(args=["run_daily.py"], returncode=1, stdout="", stderr=str(e))
        self.root.after(0, lambda: self._finish_run(result))

    def on_run(self) -> None:
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

        thread = threading.Thread(target=self._run_task_thread, args=(date_from, date_until), daemon=True)
        thread.start()


def main() -> None:
    root = tk.Tk()
    PaperBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
