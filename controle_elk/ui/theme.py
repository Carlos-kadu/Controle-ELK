import tkinter as tk
from tkinter import ttk

BG = "#10121b"
PANEL = "#1b1e2b"
FIELD = "#282c3c"
TEXT = "#f3f3fa"
MUTED = "#aeb3c8"
ACCENT = "#b7a3ff"
CONNECTED_GREEN = "#42d4a1"
HOVER = "#363c52"
BORDER = "#444b62"
DISABLED = "#75798d"
TAB_HOVER = "#202435"
TAB_ACTIVE = "#27283c"


def configure_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        ".",
        font=("Segoe UI", 10),
        background=PANEL,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        focuscolor=ACCENT,
        focusthickness=1,
    )
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TButton", padding=(13, 6), background=FIELD, borderwidth=1)
    style.map(
        "TButton",
        background=[("disabled", PANEL), ("pressed", BORDER), ("active", HOVER)],
        foreground=[("disabled", DISABLED)],
        bordercolor=[("focus", ACCENT)],
    )
    style.configure(
        "Primary.TButton", background=ACCENT, foreground="#151225", focuscolor="#151225"
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", PANEL), ("pressed", "#a08aef"), ("active", "#cabaff")],
        foreground=[("disabled", DISABLED)],
        bordercolor=[("focus", "#eee8ff")],
    )
    style.configure(
        "Stop.TButton", background="#623944", foreground="#fff1f5", focuscolor="#ffbccb"
    )
    style.map(
        "Stop.TButton",
        background=[("disabled", PANEL), ("pressed", "#70404f"), ("active", "#824b5b")],
        foreground=[("disabled", DISABLED)],
        bordercolor=[("focus", "#ffbccb")],
    )
    style.configure(
        "PaletteRemove.TButton",
        background=FIELD,
        foreground=MUTED,
        borderwidth=0,
        padding=(4, 4),
        font=("Segoe UI", 10),
    )
    style.map(
        "PaletteRemove.TButton",
        background=[("pressed", "#623944"), ("active", "#473044")],
        foreground=[("active", "#ffbccb")],
    )
    tab_images = style_tabs(root, style)
    style.layout("Target.TRadiobutton", style.layout("TButton"))
    style.configure("Target.TRadiobutton", background=FIELD, padding=(9, 5))
    style.map(
        "Target.TRadiobutton",
        background=[("disabled", PANEL), ("selected", ACCENT), ("active", HOVER)],
        foreground=[("disabled", DISABLED), ("selected", "#151225")],
        bordercolor=[("focus", ACCENT)],
    )
    for widget in ("TEntry", "TCombobox"):
        style.configure(
            widget,
            fieldbackground=FIELD,
            background=FIELD,
            foreground=TEXT,
            insertcolor=TEXT,
            selectbackground=HOVER,
            selectforeground=TEXT,
            padding=6,
        )
        style.map(
            widget,
            fieldbackground=[("disabled", PANEL), ("!disabled", FIELD)],
            foreground=[("disabled", DISABLED)],
            bordercolor=[("focus", ACCENT)],
            lightcolor=[("focus", ACCENT)],
            background=[("disabled", PANEL), ("active", HOVER)],
        )
    style.configure("TCombobox", arrowcolor=MUTED, arrowsize=12)
    style.map("TCombobox", arrowcolor=[("disabled", DISABLED), ("active", TEXT)])
    style.map(
        "Inactive.TCombobox",
        foreground=[("readonly", DISABLED)],
        arrowcolor=[("readonly", DISABLED)],
    )
    style.configure("Horizontal.TScale", background=BORDER, troughcolor=FIELD)
    style.map("Horizontal.TScale", background=[("active", ACCENT)])
    style.configure(
        "Connection.Horizontal.TProgressbar",
        background=CONNECTED_GREEN,
        troughcolor=FIELD,
        lightcolor=CONNECTED_GREEN,
        darkcolor=CONNECTED_GREEN,
        bordercolor=FIELD,
        thickness=5,
    )
    style.configure(
        "Vertical.TScrollbar", background=FIELD, troughcolor=PANEL, arrowsize=10
    )
    style.layout(
        "Vertical.TScrollbar",
        [
            (
                "Vertical.Scrollbar.trough",
                {
                    "sticky": "ns",
                    "children": [("Vertical.Scrollbar.thumb", {"sticky": "nswe"})],
                },
            ),
        ],
    )
    style.map(
        "Vertical.TScrollbar", background=[("pressed", BORDER), ("active", HOVER)]
    )
    style.configure(
        "TCheckbutton",
        background=PANEL,
        indicatorbackground=FIELD,
        indicatorforeground="#151225",
        upperbordercolor=BORDER,
        lowerbordercolor=BORDER,
        indicatormargin=(0, 0, 7, 0),
        padding=(5, 4),
    )
    style.map(
        "TCheckbutton",
        background=[("active", FIELD)],
        indicatorbackground=[("selected", ACCENT), ("active", HOVER)],
        indicatorforeground=[("disabled", DISABLED)],
    )
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", HOVER)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
    return tab_images


def style_tabs(root, style):
    def surface(background, underline):
        tile = tk.PhotoImage(master=root, width=4, height=7)
        tile.put(background, to=(0, 0, 4, 7))
        tile.put(underline, to=(0, 4, 4, 7))
        return tile

    idle = surface(BG, BORDER)
    hover = surface(TAB_HOVER, BORDER)
    selected = surface(TAB_ACTIVE, ACCENT)
    style.element_create(
        "ElkTab.surface",
        "image",
        idle,
        ("selected", selected),
        ("active", hover),
        border=(0, 0, 0, 3),
        sticky="nsew",
    )
    style.layout(
        "Elk.TNotebook",
        [
            (
                "Notebook.padding",
                {
                    "sticky": "nsew",
                    "children": [("Notebook.client", {"sticky": "nsew"})],
                },
            )
        ],
    )
    style.layout(
        "Elk.TNotebook.Tab",
        [
            (
                "ElkTab.surface",
                {
                    "sticky": "nsew",
                    "children": [
                        (
                            "Notebook.padding",
                            {
                                "sticky": "nsew",
                                "children": [
                                    (
                                        "Notebook.focus",
                                        {
                                            "sticky": "nsew",
                                            "children": [
                                                ("Notebook.label", {"sticky": "nsew"})
                                            ],
                                        },
                                    )
                                ],
                            },
                        )
                    ],
                },
            )
        ],
    )
    style.configure(
        "Elk.TNotebook",
        background=BG,
        borderwidth=0,
        padding=0,
        tabmargins=(0, 0, 0, 0),
    )
    tab_padding = (19, 12, 19, 14)
    style.configure(
        "Elk.TNotebook.Tab",
        foreground=MUTED,
        padding=tab_padding,
        font=("Segoe UI", 10, "bold"),
        expand=(0, 0, 0, 0),
    )
    style.map(
        "Elk.TNotebook.Tab",
        expand=[("selected", (0, 0, 0, 0))],
        padding=[("selected", tab_padding)],
        foreground=[("selected", ACCENT), ("active", TEXT)],
    )
    offline_selected = surface("#222537", "#656080")
    style.element_create(
        "OfflineElkTab.surface",
        "image",
        idle,
        ("selected", offline_selected),
        ("active", hover),
        border=(0, 0, 0, 3),
        sticky="nsew",
    )
    _, layout = style.layout("Elk.TNotebook.Tab")[0]
    style.layout("Offline.Elk.TNotebook.Tab", [("OfflineElkTab.surface", layout)])
    style.configure("Offline.Elk.TNotebook.Tab", foreground=DISABLED)
    style.map(
        "Offline.Elk.TNotebook.Tab",
        foreground=[("selected", "#aaa3bd"), ("active", MUTED)],
    )
    return idle, hover, selected, offline_selected
