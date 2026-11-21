import sqlite3
import tkinter as tk
from tkinter import colorchooser, ttk

from ..ble import protocol
from .dialogs import ask_name
from .scroll import update_scrollbar
from .theme import FIELD, MUTED, PANEL

DEFAULT_GRADIENT = ("#FF0000", "#FF00FF", "#0000FF")
DEFAULT_TRANSITION_SECONDS = "5"


class ColorAnimationEditor:
    def __init__(self, view, card, store, *, sequence=False):
        self.sequence = sequence
        self.name = "sequência" if sequence else "gradiente"
        self.view = view
        self.device_store = store
        self.stops = []
        self.stop_resize_job = None
        self.preview_job = None
        self.preview_key = None
        self.preview_image = None
        self.presets = {}
        self.repeat = tk.BooleanVar(value=True)
        presets = ttk.Frame(card, style="Panel.TFrame")
        presets.pack(fill="x", pady=(0, 10))
        presets.columnconfigure(1, weight=1)
        self.view.label(
            presets, "Sequências salvas" if sequence else "Gradientes salvos", bold=True
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.preset_picker = ttk.Combobox(presets, state="readonly")
        self.preset_picker.grid(row=0, column=1, sticky="nsew")
        self.load_preset_button = self.view.button(
            presets, "Carregar", self.load_preset
        )
        self.load_preset_button.grid(row=0, column=2, sticky="ns", padx=(6, 0))
        self.view.button(presets, f"Salvar {self.name}…", self.save_preset).grid(
            row=0, column=3, sticky="ns", padx=(6, 0)
        )
        self.view.label(
            card,
            "Tempo que cada cor fica acesa, em segundos."
            if sequence
            else "Tempo para chegar a cada cor. O primeiro campo vale na volta do loop.",
            color=MUTED,
        ).pack(fill="x", pady=(0, 8))
        self.preview = tk.Canvas(card, height=40, bg=FIELD, highlightthickness=0)
        self.preview.pack(fill="x", pady=(0, 10))
        self.preview.bind("<Configure>", self.schedule_preview)
        self.preview.bind("<Map>", self.schedule_preview)
        self.preview.bind("<Unmap>", self.release_preview)
        self.preview_item = self.preview.create_image(0, 0, anchor="nw")
        list_row = ttk.Frame(card, style="Panel.TFrame")
        list_row.columnconfigure(0, weight=1)
        list_row.rowconfigure(0, weight=1)
        self.stop_canvas = tk.Canvas(
            list_row, height=120, bg=PANEL, highlightthickness=0
        )
        self.stop_canvas.grid(row=0, column=0, sticky="nsew")
        self.stop_scrollbar = ttk.Scrollbar(
            list_row, orient="vertical", command=self.stop_canvas.yview
        )
        self.stop_scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.stop_scrollbar.grid_remove()
        self.stop_canvas.configure(
            yscrollcommand=lambda first, last: update_scrollbar(
                self.stop_scrollbar, first, last
            )
        )
        self.stop_rows = ttk.Frame(self.stop_canvas, style="Panel.TFrame")
        rows = self.stop_canvas.create_window(
            (0, 0), window=self.stop_rows, anchor="nw"
        )
        self.stop_rows.bind("<Configure>", self.schedule_stop_resize)
        self.stop_canvas.bind(
            "<Configure>",
            lambda event: self.stop_canvas.itemconfigure(rows, width=event.width),
        )
        for color in DEFAULT_GRADIENT:
            self.add_stop(color)
        options = ttk.Frame(card, style="Panel.TFrame")
        self.view.button(options, "+ Cor", self.add_stop).pack(side="left")
        ttk.Checkbutton(
            options,
            text="Repetir em loop",
            variable=self.repeat,
            command=self.sync_stops,
            cursor="hand2",
        ).pack(side="right")
        self.play_button = self.view.button(
            card,
            "Reproduzir",
            lambda: self.view.toggle_animation(
                action="sequencia" if sequence else "gradiente"
            ),
            primary=True,
        )
        self.play_button.pack(side="bottom", fill="x")
        brightness = ttk.Frame(card, style="Panel.TFrame")
        brightness.pack(side="bottom", fill="x", pady=(0, 10))
        self.view.brightness_slider(brightness)
        options.pack(side="bottom", fill="x", pady=(6, 0))
        list_row.pack(fill="both", expand=True)

    def load_presets(self, selected=None):
        try:
            self.presets = self.device_store.load_gradients(sequence=self.sequence)
        except (sqlite3.Error, ValueError) as error:
            self.view.status.set(f"Não foi possível ler os itens salvos: {error}")
        names = tuple(self.presets)
        self.preset_picker.configure(
            values=names, state="readonly" if names else "disabled"
        )
        self.load_preset_button.configure(state="normal" if names else "disabled")
        if names:
            self.preset_picker.current(
                names.index(selected) if selected in names else 0
            )
        else:
            self.preset_picker.set(
                "Nenhuma sequência salva" if self.sequence else "Nenhum gradiente salvo"
            )

    def values(self):
        values = [
            value.get().strip()
            if index == 0 and not (self.sequence or self.repeat.get())
            else f"{value.get().strip()}:{duration.get().strip().replace(',', '.')}"
            for index, (_, value, duration, _) in enumerate(self.stops)
        ]
        if self.repeat.get():
            values.append("loop")
        return values

    def save_preset(self):
        from ..control.commands import parse_gradient, parse_sequence

        values = self.values()
        try:
            (parse_sequence if self.sequence else parse_gradient)(values)
        except ValueError as error:
            self.view.status.set(str(error))
            return
        name = ask_name(
            self.view,
            f"Salvar {self.name}",
            "Nome da sequência" if self.sequence else "Nome do gradiente",
            "",
            hint="",
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            self.view.status.set("Informe um nome.")
            return
        try:
            added = self.device_store.save_gradient(
                name, values, sequence=self.sequence
            )
        except sqlite3.Error as error:
            self.view.status.set(f"Não foi possível salvar: {error}")
            return
        self.load_presets(name if added else self.preset_picker.get())
        self.view.status.set(
            f"{name} salvo." if added else f"O nome {name} já está em uso."
        )

    def load_preset(self):
        name = self.preset_picker.get()
        if name not in self.presets:
            return
        values = self.presets[name]
        repeat = values[-1] == "loop"
        colors = values[:-1] if repeat else values
        for row, _, _, _ in self.stops:
            row.destroy()
        self.stops.clear()
        color, _, duration = colors[0].partition(":")
        _, _, last_duration = colors[-1].partition(":")
        self.add_stop(color, duration or last_duration or DEFAULT_TRANSITION_SECONDS)
        for step in colors[1:]:
            color, _, duration = step.partition(":")
            self.add_stop(color, duration)
        self.repeat.set(repeat)
        self.sync_stops()
        self.stop_canvas.yview_moveto(0)
        self.view.status.set(f"{name} carregado. Clique em Reproduzir para começar.")

    def schedule_stop_resize(self, _=None):
        if self.stop_resize_job is None and not self.view.closing:
            self.stop_resize_job = self.view.root.after_idle(self.resize_stop_region)

    def resize_stop_region(self):
        self.stop_resize_job = None
        height = self.stop_rows.winfo_reqheight()
        self.stop_canvas.configure(
            scrollregion=(0, 0, self.stop_canvas.winfo_width(), height)
        )
        if height <= self.stop_canvas.winfo_height():
            self.stop_canvas.yview_moveto(0)

    def add_stop(self, color="#FF00FF", seconds=DEFAULT_TRANSITION_SECONDS):
        row = ttk.Frame(self.stop_rows, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 4))
        value = tk.StringVar(value=color)
        duration = tk.StringVar(value=seconds)
        swatch = tk.Button(
            row,
            width=3,
            relief="flat",
            cursor="hand2",
            command=lambda: self.pick_stop(value),
        )
        swatch.grid(row=0, column=0, sticky="ns", padx=(0, 6))
        ttk.Entry(row, textvariable=value, width=10).grid(row=0, column=1, sticky="ns")
        timing = ttk.Entry(row, textvariable=duration, width=6)
        timing.grid(row=0, column=2, sticky="ns", padx=(8, 3))
        self.view.label(row, "s", color=MUTED).grid(row=0, column=3, sticky="w")
        self.view.button(row, "Remover", lambda: self.remove_stop(row)).grid(
            row=0, column=4, sticky="ns", padx=(10, 0)
        )
        self.stops.append((row, value, duration, timing))

        def update(*_):
            try:
                rgb = protocol.parse_rgb(value.get())
            except ValueError:
                rgb = None
            color = "#" + rgb.hex() if rgb else FIELD
            swatch.configure(bg=color, activebackground=color)
            self.schedule_preview()

        value.trace_add("write", update)
        self.sync_stops()
        update()

    def remove_stop(self, row):
        if len(self.stops) <= (1 if self.sequence else 2):
            self.view.status.set(
                "A sequência precisa de pelo menos uma cor."
                if self.sequence
                else "O gradiente precisa de pelo menos duas cores."
            )
            return
        self.stops = [stop for stop in self.stops if stop[0] is not row]
        row.destroy()
        self.sync_stops()
        self.schedule_preview()

    def sync_stops(self):
        for index, (_, _, _, field) in enumerate(self.stops):
            field.configure(
                state="normal"
                if index or self.sequence or self.repeat.get()
                else "disabled"
            )
        self.schedule_stop_resize()

    def schedule_preview(self, _=None):
        if self.preview_job is None and not self.view.closing:
            self.preview_job = self.view.root.after_idle(self.draw_preview)

    def draw_preview(self):
        self.preview_job = None
        if not self.preview.winfo_ismapped():
            return
        try:
            colors = tuple(
                protocol.parse_rgb(value.get()) for _, value, _, _ in self.stops
            )
        except ValueError:
            self.preview.itemconfigure(self.preview_item, image="")
            self.preview_image = None
            self.preview_key = None
            return
        width = self.preview.winfo_width()
        height = self.preview.winfo_height()
        key = (width, height, colors)
        if not colors or width < 2 or height < 2 or key == self.preview_key:
            return
        row = []
        for x in range(width):
            if self.sequence or len(colors) == 1:
                row.append(f"#{colors[x * len(colors) // width].hex()}")
                continue
            position = x * (len(colors) - 1) / (width - 1)
            index = min(int(position), len(colors) - 2)
            fraction = position - index
            rgb = bytes(
                round(a + (b - a) * fraction)
                for a, b in zip(colors[index], colors[index + 1])
            )
            row.append(f"#{rgb.hex()}")
        band = tk.PhotoImage(master=self.preview, width=width, height=1)
        band.put("{" + " ".join(row) + "}")
        self.preview_image = band.zoom(1, height)
        self.preview.itemconfigure(self.preview_item, image=self.preview_image)
        self.preview_key = key

    def release_preview(self, _event=None):
        if self.preview_image is not None:
            self.preview.itemconfigure(self.preview_item, image="")
            self.preview_image = None
            self.preview_key = None

    def cancel_pending(self):
        for job in (self.stop_resize_job, self.preview_job):
            if job is not None:
                self.view.root.after_cancel(job)

    def pick_stop(self, value):
        _, color = colorchooser.askcolor(
            parent=self.view.root,
            title="Cor da sequência" if self.sequence else "Cor do gradiente",
        )
        if color:
            value.set(color.upper())
