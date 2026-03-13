from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG_MAIN = "#F5F7FB"
BG_PANEL = "#FFFFFF"
BORDER = "#E5E7EB"
TEXT_MAIN = "#1F2937"
TEXT_SUB = "#6B7280"
PRIMARY = "#3B82F6"
PRIMARY_HOVER = "#2563EB"
PRIMARY_ACTIVE = "#1D4ED8"
SELECT_BG = "#DBEAFE"


def apply_theme(root: tk.Tk) -> None:
    root.configure(bg=BG_MAIN)
    root.option_add("*Font", "Microsoft YaHei 10")

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    # Base containers
    style.configure("TFrame", background=BG_MAIN)
    style.configure("Sidebar.TFrame", background=BG_MAIN)
    style.configure("Main.TFrame", background=BG_MAIN)

    style.configure(
        "Card.TLabelframe",
        background=BG_PANEL,
        bordercolor=BORDER,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=BG_PANEL,
        foreground=TEXT_MAIN,
        font=("Microsoft YaHei", 12, "bold"),
    )

    # Text labels
    style.configure("TLabel", background=BG_MAIN, foreground=TEXT_MAIN)

    # Buttons
    style.configure(
        "Menu.TButton",
        font=("Microsoft YaHei", 12),
        padding=(12, 8),
        background=BG_MAIN,
        foreground=TEXT_MAIN,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Menu.TButton",
        background=[("active", "#EEF2FF")],
        foreground=[("active", PRIMARY_ACTIVE)],
    )

    style.configure(
        "MenuActive.TButton",
        font=("Microsoft YaHei", 12, "bold"),
        padding=(12, 8),
        background="#EEF2FF",
        foreground=PRIMARY_ACTIVE,
        borderwidth=0,
        relief="flat",
    )

    style.configure(
        "Primary.TButton",
        font=("Microsoft YaHei", 12, "bold"),
        padding=(16, 10),
        background=PRIMARY,
        foreground="#FFFFFF",
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Primary.TButton",
        background=[("active", PRIMARY_HOVER), ("pressed", PRIMARY_ACTIVE)],
        foreground=[("disabled", "#D1D5DB")],
    )

    style.configure(
        "Success.TButton",
        font=("Microsoft YaHei", 12, "bold"),
        padding=(14, 8),
        background=PRIMARY,
        foreground="#FFFFFF",
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Success.TButton",
        background=[("active", PRIMARY_HOVER), ("pressed", PRIMARY_ACTIVE)],
    )

    # Inputs
    style.configure(
        "TEntry",
        fieldbackground="#FFFFFF",
        foreground=TEXT_MAIN,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=8,
    )
    style.map("TEntry", bordercolor=[("focus", PRIMARY)], lightcolor=[("focus", PRIMARY)])

    style.configure(
        "TCombobox",
        fieldbackground="#FFFFFF",
        foreground=TEXT_MAIN,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        arrowsize=14,
        padding=6,
    )
    style.map(
        "TCombobox",
        bordercolor=[("focus", PRIMARY)],
        lightcolor=[("focus", PRIMARY)],
        fieldbackground=[("readonly", "#FFFFFF")],
    )

    # Table / tree
    style.configure(
        "Treeview",
        background="#FFFFFF",
        fieldbackground="#FFFFFF",
        foreground=TEXT_MAIN,
        rowheight=30,
        bordercolor=BORDER,
    )
    style.map("Treeview", background=[("selected", SELECT_BG)], foreground=[("selected", TEXT_MAIN)])

    style.configure(
        "Treeview.Heading",
        background="#F9FAFB",
        foreground=TEXT_SUB,
        bordercolor=BORDER,
        relief="flat",
        padding=8,
        font=("Microsoft YaHei", 10, "bold"),
    )
    style.map("Treeview.Heading", background=[("active", "#F3F4F6")])

    # Progress
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor="#E5E7EB",
        background=PRIMARY,
        bordercolor="#E5E7EB",
        lightcolor=PRIMARY,
        darkcolor=PRIMARY,
    )

    # Scrollbar
    style.configure(
        "Vertical.TScrollbar",
        background="#D1D5DB",
        troughcolor="#F3F4F6",
        bordercolor="#F3F4F6",
        arrowcolor=TEXT_SUB,
        relief="flat",
    )
    style.map("Vertical.TScrollbar", background=[("active", "#9CA3AF")])
