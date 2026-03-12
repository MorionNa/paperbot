from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config" / "config.yml"
SECRETS_PATH = BASE_DIR / "config" / "secrets.yml"


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


def _append_journal(name: str, publisher: str, crossref_issn: str, issn_print: str, issn_online: str) -> None:
    cfg = _load_yaml(CONFIG_PATH)
    journals = cfg.setdefault("journals", [])

    journal = {
        "name": name.strip(),
        "publisher": publisher.strip().lower(),
        "crossref_issn": crossref_issn.strip(),
    }
    if issn_print.strip():
        journal["issn_print"] = issn_print.strip()
    if issn_online.strip():
        journal["issn_online"] = issn_online.strip()

    journals.append(journal)
    _save_yaml(CONFIG_PATH, cfg)


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


def _set_date_range_and_run(date_from: str, date_until: str) -> subprocess.CompletedProcess[str]:
    cfg = _load_yaml(CONFIG_PATH)
    pipeline = cfg.setdefault("pipeline", {})
    pipeline["date_from"] = date_from.strip()
    pipeline["date_until"] = date_until.strip()
    _save_yaml(CONFIG_PATH, cfg)

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
        self.root.title("PaperBot 配置与下载")
        self.root.geometry("860x620")

        wrapper = ttk.Frame(root, padding=16)
        wrapper.pack(fill=tk.BOTH, expand=True)

        self._build_journal_section(wrapper)
        self._build_api_section(wrapper)
        self._build_run_section(wrapper)

    def _build_journal_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="1) 添加期刊到 config.yml", padding=12)
        frame.pack(fill=tk.X, pady=(0, 12))

        self.journal_name = tk.StringVar()
        self.journal_publisher = tk.StringVar()
        self.journal_crossref_issn = tk.StringVar()
        self.journal_issn_print = tk.StringVar()
        self.journal_issn_online = tk.StringVar()

        fields = [
            ("期刊名称", self.journal_name),
            ("出版社（elsevier/wiley/springer/ieee 等）", self.journal_publisher),
            ("Crossref ISSN", self.journal_crossref_issn),
            ("ISSN (print，可选)", self.journal_issn_print),
            ("ISSN (online，可选)", self.journal_issn_online),
        ]

        for i, (label, var) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=4)
            ttk.Entry(frame, textvariable=var, width=56).grid(row=i, column=1, sticky=tk.W, padx=8, pady=4)

        ttk.Button(frame, text="添加期刊", command=self.on_add_journal).grid(
            row=len(fields), column=1, sticky=tk.E, pady=(8, 0)
        )

    def _build_api_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="2) 设置 API Key 到 secret.yml", padding=12)
        frame.pack(fill=tk.X, pady=(0, 12))

        self.elsevier_key = tk.StringVar()
        self.wiley_key = tk.StringVar()
        self.springer_key = tk.StringVar()
        self.ieee_key = tk.StringVar()

        fields = [
            ("Elsevier API Key", self.elsevier_key),
            ("Wiley TDM Token", self.wiley_key),
            ("Springer API Key", self.springer_key),
            ("IEEE API Key", self.ieee_key),
        ]

        for i, (label, var) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=4)
            ttk.Entry(frame, textvariable=var, width=56, show="*").grid(
                row=i, column=1, sticky=tk.W, padx=8, pady=4
            )

        ttk.Button(frame, text="确认保存 Key", command=self.on_save_keys).grid(
            row=len(fields), column=1, sticky=tk.E, pady=(8, 0)
        )

    def _build_run_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="3) 按时间范围下载并运行 run_daily.py", padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        self.date_from = tk.StringVar()
        self.date_until = tk.StringVar()

        ttk.Label(frame, text="开始时间 (YYYY-MM-DD)").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(frame, textvariable=self.date_from, width=28).grid(row=0, column=1, sticky=tk.W, padx=8, pady=4)

        ttk.Label(frame, text="结束时间 (YYYY-MM-DD)").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(frame, textvariable=self.date_until, width=28).grid(row=1, column=1, sticky=tk.W, padx=8, pady=4)

        ttk.Button(frame, text="下载并运行", command=self.on_run).grid(row=2, column=1, sticky=tk.E, pady=(8, 8))

        self.output_box = tk.Text(frame, height=12, wrap="word")
        self.output_box.grid(row=3, column=0, columnspan=2, sticky="nsew")
        frame.rowconfigure(3, weight=1)
        frame.columnconfigure(1, weight=1)

    def on_add_journal(self) -> None:
        if not self.journal_name.get().strip() or not self.journal_crossref_issn.get().strip():
            messagebox.showerror("输入错误", "请至少填写期刊名称和 Crossref ISSN")
            return

        _append_journal(
            name=self.journal_name.get(),
            publisher=self.journal_publisher.get(),
            crossref_issn=self.journal_crossref_issn.get(),
            issn_print=self.journal_issn_print.get(),
            issn_online=self.journal_issn_online.get(),
        )
        messagebox.showinfo("成功", f"已添加期刊：{self.journal_name.get().strip()}")

    def on_save_keys(self) -> None:
        _save_api_keys(
            elsevier_key=self.elsevier_key.get(),
            wiley_key=self.wiley_key.get(),
            springer_key=self.springer_key.get(),
            ieee_key=self.ieee_key.get(),
        )
        messagebox.showinfo("成功", f"API Keys 已保存到 {SECRETS_PATH}")

    def on_run(self) -> None:
        date_from = self.date_from.get().strip()
        date_until = self.date_until.get().strip()
        if not date_from or not date_until:
            messagebox.showerror("输入错误", "请填写开始时间和结束时间")
            return

        self.output_box.delete("1.0", tk.END)
        self.output_box.insert(tk.END, "正在运行 run_daily.py，请稍候...\n")
        self.root.update_idletasks()

        result = _set_date_range_and_run(date_from=date_from, date_until=date_until)
        self.output_box.insert(tk.END, "\n[STDOUT]\n" + (result.stdout or ""))
        self.output_box.insert(tk.END, "\n[STDERR]\n" + (result.stderr or ""))

        if result.returncode == 0:
            messagebox.showinfo("完成", "run_daily.py 已执行完成")
        else:
            messagebox.showerror("执行失败", f"run_daily.py 返回码：{result.returncode}")


def main() -> None:
    root = tk.Tk()
    PaperBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
