import tkinter as tk
from tkinter import ttk

from .theme import MUTED, PANEL


def ask_name(view, title, heading, initial, *, context=None, hint):
    dialog = tk.Toplevel(view.root)
    dialog.withdraw()
    dialog.title(title)
    dialog.transient(view.root)
    dialog.resizable(False, False)
    dialog.configure(bg=PANEL)
    name = tk.StringVar(master=dialog, value=initial)
    count = tk.StringVar(master=dialog)
    result = None

    content = view.panel(dialog)
    content.pack(fill="both", expand=True, padx=7, pady=6)
    view.label(content, heading, size=16, bold=True).pack(
        fill="x", pady=(0, 0 if context else 12)
    )
    if context:
        view.label(content, context, color=MUTED).pack(fill="x", pady=(1, 14))
    entry = ttk.Entry(content, textvariable=name, width=38)
    entry.pack(fill="x")
    help_row = ttk.Frame(content, style="Panel.TFrame")
    help_row.pack(fill="x", pady=(6, 16))
    if hint:
        view.label(help_row, hint, color=MUTED).pack(side="left", padx=(0, 10))
    view.label(help_row, variable=count, color=MUTED).pack(side="right")
    actions = ttk.Frame(content, style="Panel.TFrame")
    actions.pack(fill="x")

    def save(_=None):
        nonlocal result
        if len(name.get().strip()) <= 40:
            result = name.get()
            dialog.destroy()

    save_button = view.button(actions, "Salvar", save, primary=True)
    save_button.pack(side="right")
    view.button(actions, "Cancelar", dialog.destroy).pack(side="right", padx=(0, 6))

    def update_count(*_):
        length = len(name.get().strip())
        count.set(f"{length}/40")
        save_button.configure(state="normal" if length <= 40 else "disabled")

    name.trace_add("write", update_count)
    update_count()
    dialog.bind("<Return>", save)
    dialog.bind("<Escape>", lambda _: dialog.destroy())
    dialog.update_idletasks()
    width, height = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
    x = view.root.winfo_rootx() + (view.root.winfo_width() - width) // 2
    y = view.root.winfo_rooty() + (view.root.winfo_height() - height) // 2
    dialog.geometry(f"{width}x{height}{x:+d}{y:+d}")
    if dialog.tk.call("tk", "windowingsystem") == "win32":
        use_dark_title_bar(dialog)
    dialog.deiconify()
    dialog.wait_visibility()
    dialog.grab_set()
    entry.focus_set()
    entry.selection_range(0, tk.END)
    view.root.wait_window(dialog)
    return result


def use_dark_title_bar(window):
    import ctypes
    from ctypes import wintypes

    frame = wintypes.HWND(int(str(window.wm_frame()), 0))
    enabled = ctypes.c_int(1)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        frame, 20, ctypes.byref(enabled), ctypes.sizeof(enabled)
    )
