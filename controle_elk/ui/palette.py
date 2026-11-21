import sqlite3
import tkinter as tk
from tkinter import ttk

from ..ble import protocol
from .scroll import update_scrollbar
from .theme import ACCENT, FIELD, HOVER, PANEL, TEXT


class SolidPalette:
    def __init__(self, view, card, store):
        self.view = view
        self.device_store = store
        self.saved_colors = []
        self.saved_resize_job = None
        self.saved_palette = ttk.Frame(card, style="Panel.TFrame")
        self.view.label(self.saved_palette, "Minhas cores", size=12, bold=True).pack(
            fill="x", pady=(0, 8)
        )
        viewport = ttk.Frame(self.saved_palette, style="Panel.TFrame")
        viewport.pack(fill="x")
        viewport.columnconfigure(0, weight=1)
        self.saved_canvas = tk.Canvas(
            viewport, height=108, bg=PANEL, highlightthickness=0
        )
        self.saved_canvas.grid(row=0, column=0, sticky="ew")
        self.saved_scrollbar = ttk.Scrollbar(
            viewport, orient="vertical", command=self.saved_canvas.yview
        )
        self.saved_scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.saved_scrollbar.grid_remove()
        self.saved_canvas.configure(
            yscrollcommand=lambda first, last: update_scrollbar(
                self.saved_scrollbar, first, last
            )
        )
        self.saved_color_grid = ttk.Frame(self.saved_canvas, style="Panel.TFrame")
        container = self.saved_canvas.create_window(
            (0, 0), window=self.saved_color_grid, anchor="nw"
        )
        self.saved_canvas.bind(
            "<Configure>",
            lambda event: self.saved_canvas.itemconfigure(container, width=event.width),
        )
        self.saved_color_grid.bind("<Configure>", self.schedule_saved_resize)
        for column in range(6):
            self.saved_color_grid.columnconfigure(
                column, weight=1, uniform="saved_colors"
            )

    def schedule_saved_resize(self, _=None):
        if self.saved_resize_job is None and not self.view.closing:
            self.saved_resize_job = self.view.root.after_idle(self.resize_saved_palette)

    def cancel_pending(self):
        if self.saved_resize_job is not None:
            self.view.root.after_cancel(self.saved_resize_job)

    def resize_saved_palette(self):
        self.saved_resize_job = None
        height = self.saved_color_grid.winfo_reqheight()
        self.saved_canvas.configure(
            scrollregion=(0, 0, self.saved_canvas.winfo_width(), height)
        )
        if height <= self.saved_canvas.winfo_height():
            self.saved_canvas.yview_moveto(0)

    def load_saved_colors(self):
        try:
            self.saved_colors = self.device_store.load_colors()
        except sqlite3.Error as error:
            self.view.status.set(f"Não foi possível ler as cores salvas: {error}")
            return
        self.draw_saved_palette()

    def draw_saved_palette(self):
        for child in self.saved_color_grid.winfo_children():
            child.destroy()
        if not self.saved_colors:
            self.saved_palette.pack_forget()
            return
        self.saved_palette.pack(fill="x", pady=(16, 0))
        for index, color in enumerate(self.saved_colors):
            tile = tk.Frame(self.saved_color_grid, bg=FIELD)
            tile.grid(
                row=index // 6, column=index % 6, sticky="ew", padx=(0, 8), pady=(0, 8)
            )
            preview = tk.PhotoImage(master=self.view.root, width=19, height=19)
            preview.put(color, to=(2, 0, 17, 19))
            preview.put(color, to=(0, 2, 19, 17))
            swatch = tk.Button(
                tile,
                text=color,
                image=preview,
                compound="left",
                anchor="w",
                bg=FIELD,
                fg=TEXT,
                activebackground=HOVER,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                padx=6,
                pady=6,
                cursor="hand2",
                highlightthickness=1,
                highlightbackground=FIELD,
                highlightcolor=ACCENT,
                font=("Consolas", 9),
                command=lambda color=color: self.view.set_color(color),
            )
            swatch.preview = preview
            remove = ttk.Button(
                tile,
                text="×",
                style="PaletteRemove.TButton",
                cursor="hand2",
                width=2,
                command=lambda color=color: self.remove_saved_color(color),
            )
            remove.pack(side="right", padx=(0, 3))
            swatch.pack(side="left", fill="both", expand=True)
        self.schedule_saved_resize()

    def save_solid_color(self):
        try:
            color = "#" + protocol.parse_rgb(self.view.rgb.get()).hex().upper()
            added = self.device_store.save_color(color)
        except (ValueError, sqlite3.Error) as error:
            self.view.status.set(str(error))
            return
        self.view.rgb.set(color)
        self.load_saved_colors()
        self.view.status.set(
            f"Cor {color} salva." if added else f"A cor {color} já está na paleta."
        )

    def remove_saved_color(self, color):
        try:
            self.device_store.remove_color(color)
        except sqlite3.Error as error:
            self.view.status.set(f"Não foi possível remover a cor: {error}")
            return
        self.load_saved_colors()
        self.view.status.set(f"Cor {color} removida.")
