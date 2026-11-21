import concurrent.futures
import queue
import sqlite3
import threading
import tkinter as tk
from dataclasses import replace
from tkinter import colorchooser, ttk

from ..ble import protocol
from ..storage.preferences import DEFAULT_BRIGHTNESS, DeviceStore, SavedDevice
from .dialogs import ask_name
from .palette import SolidPalette
from .theme import (
    ACCENT,
    BG,
    BORDER,
    CONNECTED_GREEN,
    MUTED,
    PANEL,
    TEXT,
    configure_theme,
)

PRESETS = ("#FF0000", "#FF6500", "#FFFF00", "#00FF00", "#0000FF", "#FF00FF", "#FFFFFF")
MAX_CONNECTIONS = 3
ALL_TARGETS = "all"
MODE_COMMANDS = {"ligar", "desligar", "cor", "efeito"}
EFFECT_LABELS = {
    "salto-rgb": "Troca rápida · RGB",
    "salto-7-cores": "Troca rápida · 7 cores",
    "degrade-rgb": "Transição suave · RGB",
    "degrade-7-cores": "Transição suave · 7 cores",
    "degrade-vermelho": "Transição suave · Vermelho",
    "degrade-verde": "Transição suave · Verde",
    "degrade-azul": "Transição suave · Azul",
    "degrade-amarelo": "Transição suave · Amarelo",
    "degrade-ciano": "Transição suave · Ciano",
    "degrade-magenta": "Transição suave · Magenta",
    "degrade-branco": "Transição suave · Branco",
    "degrade-vermelho-verde": "Transição suave · Vermelho / Verde",
    "degrade-vermelho-azul": "Transição suave · Vermelho / Azul",
    "degrade-verde-azul": "Transição suave · Verde / Azul",
    "pisca-7-cores": "Piscar · 7 cores",
    "pisca-vermelho": "Piscar · Vermelho",
    "pisca-verde": "Piscar · Verde",
    "pisca-azul": "Piscar · Azul",
    "pisca-amarelo": "Piscar · Amarelo",
    "pisca-ciano": "Piscar · Ciano",
    "pisca-magenta": "Piscar · Magenta",
    "pisca-branco": "Piscar · Branco",
}
EFFECT_BY_LABEL = {label: effect for effect, label in EFFECT_LABELS.items()}


class Desktop:
    def __init__(self, root, device_store=None, *, open_hotkeys=None):
        self.root = root
        self.open_hotkeys = open_hotkeys
        self.root.title("Controle de fitas ELK")
        self.root.geometry("930x765")
        self.root.minsize(860, 700)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.results = queue.SimpleQueue()
        self.loop = None
        self.pending_results = 0
        self.poll_job = None
        self.connections = {}
        self.lost_connections = queue.SimpleQueue()
        self.targets = []
        self.device_store = device_store if device_store is not None else DeviceStore()
        self.saved_devices = {}
        self.last_device_address = None
        self.sliders = []
        self.slider_updates = {}
        self.slider_timer = None
        self.brightness_save_job = None
        self.sending = False
        self.deferred_action = None
        self.mode_controls = []
        self.animation_editors = {}
        self.busy = False
        self.playing = False
        self.animation_request = None
        self.last_animation_values = {}
        self.reconnecting = False
        self.closing = False
        self.destroyed = False
        self.pending = None
        self.connecting = None
        self.status = tk.StringVar(value="Clique em Buscar para encontrar suas fitas.")
        self.target = tk.StringVar()
        self.variant = tk.StringVar(value="4")
        self.effect = tk.StringVar(value=EFFECT_LABELS["degrade-rgb"])
        self.rgb = tk.StringVar(value=PRESETS[0])
        try:
            self.saved_brightness = self.device_store.load_brightness()
        except (OSError, sqlite3.Error):
            self.saved_brightness = DEFAULT_BRIGHTNESS
        self.brightness = tk.IntVar(value=self.saved_brightness)
        self.speed = tk.IntVar(value=50)
        self.control_target = tk.StringVar()
        self.control_signature = ()
        self.control_buttons = []
        self.connection_text = tk.StringVar(value="Nenhuma fita conectada")
        self.tab_images = configure_theme(self.root)
        self.build()
        self.load_saved_devices()
        self.palette.load_saved_colors()
        self.refresh()

    @staticmethod
    def run_worker(loop):
        import asyncio

        asyncio.set_event_loop(loop)
        try:
            loop.run_forever()
        finally:
            loop.close()

    def label(
        self,
        parent,
        text=None,
        *,
        size=10,
        color=TEXT,
        bg=PANEL,
        variable=None,
        bold=False,
    ):
        return tk.Label(
            parent,
            text=text,
            textvariable=variable,
            bg=bg,
            fg=color,
            anchor="w",
            font=("Segoe UI", size, "bold" if bold else "normal"),
        )

    def button(self, parent, text, action, *, primary=False):
        return ttk.Button(
            parent,
            text=text,
            command=action,
            cursor="hand2",
            width=0,
            style="Primary.TButton" if primary else "TButton",
        )

    def panel(self, parent):
        return ttk.Frame(parent, style="Panel.TFrame", padding=15)

    def build(self):
        body = tk.Frame(self.root, bg=BG, padx=24, pady=18)
        body.pack(fill="both", expand=True)
        heading = tk.Frame(body, bg=BG)
        heading.pack(fill="x")
        self.label(heading, "Controle de fitas ELK", size=24, bold=True, bg=BG).pack(
            side="left"
        )
        if self.open_hotkeys is not None:
            self.button(heading, "Atalhos", self.open_hotkeys).pack(side="right")
        self.label(body, variable=self.status, color=MUTED, bg=BG).pack(
            fill="x", pady=(3, 14)
        )

        self.build_header(body)
        self.tabs = ttk.Notebook(body, style="Elk.TNotebook")
        self.tabs.pack(fill="both", expand=True)
        self.solid_tab = self.panel(self.tabs)
        self.effects_tab = self.panel(self.tabs)
        self.gradient_tab = self.panel(self.tabs)
        self.sequence_tab = self.panel(self.tabs)
        self.tabs.add(self.solid_tab, text="Cores sólidas")
        self.tabs.add(self.effects_tab, text="Efeitos da fita")
        self.tabs.add(self.gradient_tab, text="Gradiente personalizado")
        self.tabs.add(self.sequence_tab, text="Sequência de cores")
        self.tabs.enable_traversal()
        self.build_solid(self.solid_tab)
        self.build_effects(self.effects_tab)
        self.tabs.bind("<<NotebookTabChanged>>", self.open_animation_tab)
        self.root.bind("<MouseWheel>", self.scroll_lists, add="+")

    def open_animation_tab(self, _event):
        selected = self.tabs.select()
        if selected == str(self.gradient_tab):
            self.animation_editor("gradiente")
        elif selected == str(self.sequence_tab):
            self.animation_editor("sequencia")

    def animation_editor(self, action):
        if action not in self.animation_editors:
            from .color_animation_editor import ColorAnimationEditor

            sequence = action == "sequencia"
            tab = self.sequence_tab if sequence else self.gradient_tab
            editor = ColorAnimationEditor(
                self, tab, self.device_store, sequence=sequence
            )
            self.animation_editors[action] = editor
            editor.load_presets()
            self.refresh()
        return self.animation_editors[action]

    def build_header(self, body):
        header = self.panel(body)
        header.pack(fill="x", pady=(0, 14))
        device_actions = ttk.Frame(header, style="Panel.TFrame")
        device_actions.pack(fill="x")
        device_actions.columnconfigure(1, weight=1)
        self.label(device_actions, "Controlar", bold=True).grid(
            row=0, column=0, sticky="w", padx=(0, 9)
        )
        self.control_picker = ttk.Frame(device_actions, style="Panel.TFrame")
        self.control_picker.grid(row=0, column=1, sticky="w")
        power = ttk.Frame(device_actions, style="Panel.TFrame")
        power.grid(row=0, column=2, sticky="e", padx=(8, 0))
        power.columnconfigure((0, 2), uniform="power", weight=1)
        power.columnconfigure(1, minsize=6)
        for column, action in enumerate(("ligar", "desligar")):
            button = self.button(
                power, action.title(), lambda action=action: self.command(action)
            )
            button.grid(row=0, column=column * 2, sticky="nsew")
            self.mode_controls.append(button)

        tk.Frame(header, bg=BORDER, height=1).pack(fill="x", pady=(10, 8))
        status_row = ttk.Frame(header, style="Panel.TFrame")
        status_row.pack(fill="x")
        self.label(status_row, "Conexões Bluetooth", bold=True).pack(side="left")
        connection_status = ttk.Frame(status_row, style="Panel.TFrame")
        connection_status.pack(side="right")
        self.connection_label = self.label(
            connection_status, variable=self.connection_text, color=MUTED
        )
        self.connection_label.pack(side="right")
        self.connection_progress = ttk.Progressbar(
            connection_status,
            mode="indeterminate",
            length=36,
            maximum=12,
            style="Connection.Horizontal.TProgressbar",
        )
        devices = ttk.Frame(header, style="Panel.TFrame")
        devices.pack(fill="x", pady=(5, 0))
        devices.columnconfigure(0, weight=1)
        self.target_box = ttk.Combobox(
            devices, textvariable=self.target, state="readonly"
        )
        self.target_box.grid(row=0, column=0, sticky="nsew")
        self.target_box.bind("<<ComboboxSelected>>", lambda _: self.selection_changed())
        self.variant_label = self.label(devices, "Variante", color=MUTED)
        self.variant_label.grid(row=0, column=1, padx=(8, 4))
        self.variant_box = ttk.Combobox(
            devices, textvariable=self.variant, values=("4", "0"), width=3
        )
        self.variant_box.grid(row=0, column=2, sticky="ns")
        self.scan_button = self.button(devices, "Buscar", self.scan)
        self.scan_button.grid(row=0, column=3, sticky="ns", padx=(8, 6))
        self.connect_button = self.button(
            devices, "Conectar", self.toggle_connection, primary=True
        )
        self.connect_button.grid(row=0, column=4, sticky="ns")
        self.rename_button = self.button(devices, "Renomear", self.rename_device)
        self.rename_button.grid(row=0, column=5, sticky="ns", padx=(12, 0))
        self.forget_button = self.button(devices, "Esquecer", self.forget_device)
        self.forget_button.grid(row=0, column=6, sticky="ns", padx=(6, 0))

    def build_solid(self, card):
        self.label(card, "Cor", size=17, bold=True).pack(fill="x", pady=(0, 8))
        palette = ttk.Frame(card, style="Panel.TFrame")
        palette.pack(fill="x")
        for column, color in enumerate(PRESETS):
            palette.columnconfigure(column, weight=1, uniform="swatches")
            swatch = tk.Button(
                palette,
                bg=color,
                activebackground=color,
                width=3,
                height=2,
                relief="flat",
                cursor="hand2",
                command=lambda color=color: self.set_color(color),
            )
            swatch.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 6 if column < len(PRESETS) - 1 else 0),
            )
        color_row = ttk.Frame(card, style="Panel.TFrame")
        color_row.pack(fill="x", pady=(6, 0))
        color_row.columnconfigure(3, weight=1)
        color_entry = ttk.Entry(color_row, textvariable=self.rgb, width=12)
        color_entry.grid(row=0, column=0, sticky="ns")
        color_entry.bind("<Return>", self.apply_typed_color)
        color_entry.bind("<KP_Enter>", self.apply_typed_color)
        apply_color = self.button(color_row, "Aplicar", self.apply_typed_color)
        apply_color.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.mode_controls.append(apply_color)
        self.button(color_row, "Escolher…", self.choose_color).grid(
            row=0, column=2, sticky="ns", padx=(6, 0)
        )
        self.button(
            color_row, "+ Salvar cor", lambda: self.palette.save_solid_color()
        ).grid(row=0, column=4, sticky="ns")

        self.brightness_slider(card)
        self.palette = SolidPalette(self, card, self.device_store)

    def build_effects(self, card):
        self.label(card, "Efeito de fábrica", size=17, bold=True).pack(
            fill="x", pady=(0, 8)
        )
        effect_row = ttk.Frame(card, style="Panel.TFrame")
        effect_row.pack(fill="x")
        effect_row.columnconfigure(0, weight=1)
        ttk.Combobox(
            effect_row,
            textvariable=self.effect,
            values=tuple(EFFECT_BY_LABEL),
            state="readonly",
            width=18,
        ).grid(row=0, column=0, sticky="nsew")
        activate = self.button(
            effect_row,
            "Ativar",
            lambda: self.activate_effect(EFFECT_BY_LABEL[self.effect.get()]),
        )
        activate.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.mode_controls.append(activate)
        self.speed_slider = self.slider(
            card, "Velocidade do efeito", self.speed, 0, 183, "", "velocidade"
        )
        self.brightness_slider(card)

    def brightness_slider(self, parent):
        return self.slider(parent, "Brilho", self.brightness, 1, 100, "%", "brilho")

    def slider(self, parent, title, value, low, high, suffix, command):
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=(10, 0))
        amount = tk.StringVar(value=f"{value.get()}{suffix}")
        self.label(row, title, bold=True).pack(side="left")
        self.label(row, variable=amount, color=ACCENT).pack(side="right")
        value.trace_add("write", lambda *_: amount.set(f"{value.get()}{suffix}"))
        slider = ttk.Scale(
            parent,
            from_=low,
            to=high,
            variable=value,
            takefocus=True,
            command=lambda _: self.queue_slider(command, value.get()),
        )
        slider.pack(fill="x", pady=(5, 0))
        slider.bind(
            "<ButtonRelease-1>", lambda _: self.schedule_slider_flush(delay=0), add="+"
        )
        self.sliders.append((slider, command))
        return slider

    def queue_slider(self, action, value):
        if action == "brilho" and not self.closing:
            if self.brightness_save_job is not None:
                self.root.after_cancel(self.brightness_save_job)
            self.brightness_save_job = self.root.after(350, self.save_brightness)
        targets = tuple(self.active_connections())
        if targets and not self.closing and (not self.playing or action == "brilho"):
            self.slider_updates[action] = (targets, value)
            self.schedule_slider_flush()

    def save_brightness(self):
        self.brightness_save_job = None
        value = self.brightness.get()
        if value == self.saved_brightness:
            return
        try:
            self.device_store.save_brightness(value)
        except (OSError, sqlite3.Error) as error:
            self.status.set(f"Não foi possível salvar o brilho: {error}")
        else:
            self.saved_brightness = value

    def schedule_slider_flush(self, delay=65):
        if not self.slider_updates or self.busy or self.closing:
            return
        if self.slider_timer is not None:
            if delay:
                return
            self.root.after_cancel(self.slider_timer)
        self.slider_timer = self.root.after(delay, self.flush_slider)

    def flush_slider(self):
        self.slider_timer = None
        if self.busy or self.closing:
            return
        current = tuple(self.active_connections())
        for action in tuple(self.slider_updates):
            targets, value = self.slider_updates.pop(action)
            if targets == current and (not self.playing or action == "brilho"):
                self.send_slider_value(targets, action, value)
                return

    def send_slider_value(self, targets, action, value):
        from ..control.session import command_group

        def finished(_, error):
            self.status.set(
                error
                or (
                    f"Brilho ajustado para {value}%."
                    if action == "brilho"
                    else f"Velocidade ajustada para {value}."
                )
            )

        self.operation(
            command_group(targets, action, [str(value)]),
            self.status.get(),
            finished,
            sending=True,
        )

    def scroll_lists(self, event):
        for canvas, scrollbar in (
            (self.palette.saved_canvas, self.palette.saved_scrollbar),
            *(
                (editor.stop_canvas, editor.stop_scrollbar)
                for editor in self.animation_editors.values()
            ),
        ):
            if scrollbar.winfo_ismapped():
                widget = event.widget
                while widget is not None:
                    if widget is canvas:
                        canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
                        return "break"
                    widget = getattr(widget, "master", None)

    def choose_color(self):
        _, color = colorchooser.askcolor(parent=self.root, title="Cor da fita")
        if color:
            self.set_color(color.upper())

    def set_color(self, color, *, on_success=None):
        self.rgb.set(color)
        if self.active_connections():
            self.command("cor", color, on_success=on_success)

    def next_preset_color(self, *, on_success=None):
        current = self.rgb.get().strip().upper()
        index = PRESETS.index(current) + 1 if current in PRESETS else 0
        self.set_color(PRESETS[index % len(PRESETS)], on_success=on_success)

    def activate_effect(self, effect, *, on_success=None):
        self.effect.set(EFFECT_LABELS[effect])
        self.command("efeito", effect, on_success=on_success)

    def apply_typed_color(self, _event=None):
        try:
            rgb = protocol.parse_rgb(self.rgb.get())
        except ValueError as error:
            self.status.set(str(error))
        else:
            self.set_color("#" + rgb.hex().upper())
        return "break"

    def submit(self, coroutine, done):
        import asyncio

        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            threading.Thread(
                target=self.run_worker, args=(self.loop,), name="elk-ble", daemon=True
            ).start()
        wake = not self.pending_results or self.busy or self.closing
        self.pending_results += 1
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        future.add_done_callback(lambda result: self.results.put((done, result)))
        if wake and self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        self.schedule_poll()
        return future

    def schedule_poll(self):
        if self.poll_job is not None:
            return
        hidden = self.root.state() == "withdrawn"
        if self.pending_results and (self.busy or self.closing or not self.playing):
            interval = 80 if hidden else 30
        elif self.connections or self.pending_results:
            interval = 300 if hidden else 120
        else:
            return
        self.poll_job = self.root.after(interval, self.poll)

    def poll(self):
        self.poll_job = None
        while not self.results.empty():
            done, future = self.results.get()
            self.pending_results -= 1
            try:
                result = future.result()
            except concurrent.futures.CancelledError:
                continue
            except Exception as error:
                done(None, str(error) or type(error).__name__)
            else:
                done(result, None)
            if self.destroyed:
                return
        if not self.closing and not self.busy:
            self.handle_disconnects()
        self.schedule_poll()

    def refresh(self):
        self.refresh_control_picker()
        active = self.active_connections()
        selectable = not self.busy or self.sending
        for slider, action in self.sliders:
            ready = active and selectable and (not self.playing or action == "brilho")
            slider.configure(state="normal" if ready else "disabled")
        for button in self.mode_controls:
            button.configure(state="normal" if active and selectable else "disabled")
        current_action = self.animation_request[2] if self.animation_request else None
        for action, editor in self.animation_editors.items():
            can_cancel = self.reconnecting and current_action == action
            playing = self.playing and current_action == action
            editor.play_button.configure(
                text="Cancelar" if can_cancel else "Parar" if playing else "Reproduzir",
                style="Stop.TButton" if playing or can_cancel else "Primary.TButton",
                state="normal"
                if can_cancel or (selectable and (playing or active))
                else "disabled",
            )
        self.scan_button.configure(state="normal" if selectable else "disabled")
        self.target_box.configure(state="readonly" if selectable else "disabled")
        target = self.selected()
        connected = target is not None and target.label in self.connections
        if target and target.model == protocol.BLEDOM:
            self.variant_label.grid()
            self.variant_box.grid()
            self.variant_box.configure(
                state="readonly" if selectable and not connected else "disabled"
            )
        else:
            self.variant_label.grid_remove()
            self.variant_box.grid_remove()
        can_connect = target is not None and len(self.connections) < MAX_CONNECTIONS
        self.connect_button.configure(
            text="Desconectar" if connected else "Conectar",
            state="normal" if selectable and (connected or can_connect) else "disabled",
        )
        if target and target.label in self.saved_devices:
            self.rename_button.grid()
            self.rename_button.configure(state="normal" if selectable else "disabled")
            self.forget_button.grid()
            self.forget_button.configure(
                state="normal" if selectable and not connected else "disabled"
            )
        else:
            self.rename_button.grid_remove()
            self.forget_button.grid_remove()
        profiles = [connection.profile for _, connection in active]
        if profiles and all(profile is not None for profile in profiles):
            max_speed = min(profile.max_speed for profile in profiles)
            if float(self.speed_slider.cget("to")) != max_speed:
                self.speed_slider.configure(to=max_speed)
            if self.speed.get() > max_speed:
                self.speed.set(max_speed)
        count = len(self.connections)
        tab_style = "Elk.TNotebook" if count else "Offline.Elk.TNotebook"
        if self.tabs.cget("style") != tab_style:
            self.tabs.configure(style=tab_style)
        state = (
            f"● {count} fitas conectadas"
            if count > 1
            else "● 1 fita conectada"
            if count
            else "○ Nenhuma fita conectada"
        )
        connecting = self.connecting is not None
        if connecting:
            state = "Reconectando…" if self.reconnecting else "Conectando…"
            if not self.connection_progress.winfo_manager():
                self.connection_progress.pack(side="left", padx=(0, 7))
                self.connection_progress.start(55)
        elif self.connection_progress.winfo_manager():
            self.connection_progress.stop()
            self.connection_progress.pack_forget()
        self.connection_text.set(state)
        self.connection_label.configure(
            fg=CONNECTED_GREEN if connecting or count else MUTED
        )

    def refresh_control_picker(self):
        choices = [(label, self.short_device_name(label)) for label in self.connections]
        if len(choices) > 1:
            choices.append((ALL_TARGETS, "Todas"))
        allowed = {label for label, _ in choices}
        if self.control_target.get() not in allowed and not self.reconnecting:
            self.control_target.set(choices[0][0] if choices else "")
        signature = tuple(choices)
        if signature != self.control_signature:
            for button in self.control_buttons:
                button.destroy()
            self.control_buttons.clear()
            for label, name in choices:
                button = ttk.Radiobutton(
                    self.control_picker,
                    text=name,
                    value=label,
                    variable=self.control_target,
                    command=self.refresh,
                    style="Target.TRadiobutton",
                    takefocus=True,
                )
                button.pack(side="left", padx=(4, 0))
                self.control_buttons.append(button)
            self.control_signature = signature
        for button in self.control_buttons:
            button.configure(
                state="disabled" if self.busy and not self.sending else "normal"
            )
        if choices:
            self.control_picker.grid()
        else:
            self.control_picker.grid_remove()

    def selected(self):
        index = self.target_box.current()
        return self.targets[index] if 0 <= index < len(self.targets) else None

    def selection_changed(self):
        target = self.selected()
        saved = self.saved_devices.get(target.label) if target else None
        self.variant.set(
            saved.variant
            if saved and saved.variant in protocol.BLEDOM_PROFILES
            else "4"
        )
        self.refresh()

    def short_device_name(self, label):
        saved = self.saved_devices.get(label)
        if saved and saved.name:
            return saved.name if len(saved.name) <= 18 else saved.name[:17] + "…"
        return f"{label.split()[0]} · {label[-5:]}"

    def populate_devices(self, preferred=None):
        options = []
        for target in self.targets:
            saved = self.saved_devices.get(target.label)
            if saved and saved.name:
                options.append(f"{saved.name} · {target.label}")
            else:
                options.append(f"{target.label} · Salva" if saved else target.label)
        self.target_box.configure(values=options)
        if self.targets:
            index = next(
                (
                    i
                    for i, target in enumerate(self.targets)
                    if target.label == preferred
                ),
                0,
            )
            self.target_box.current(index)
        else:
            self.target.set("")
        self.selection_changed()

    def load_saved_devices(self):
        try:
            self.targets = self.device_store.load()
            self.last_device_address = self.device_store.load_last_device()
        except sqlite3.Error as error:
            self.status.set(f"Não foi possível ler as fitas salvas: {error}")
            return
        self.saved_devices = {target.label: target for target in self.targets}
        self.populate_devices()
        if self.targets:
            self.status.set("Escolha uma fita e clique em Conectar.")

    def connect_last_device(self, *, on_success=None):
        saved = next(
            (
                device
                for device in self.saved_devices.values()
                if device.address == self.last_device_address
            ),
            None,
        )
        if saved is None and len(self.saved_devices) == 1:
            saved = next(iter(self.saved_devices.values()))
        if saved is None:
            self.status.set("Escolha a fita que você quer conectar.")
            return False
        if saved.label not in self.connections:
            self.populate_devices(saved.label)
            self.toggle_connection(on_success=on_success)
        return True

    def rename_device(self):
        target = self.selected()
        saved = self.saved_devices.get(target.label) if target else None
        if saved is None:
            return
        value = ask_name(
            self,
            "Renomear fita",
            "Nome da fita",
            saved.name or "",
            context=saved.label,
            hint="Deixe em branco para usar o nome Bluetooth.",
        )
        if value is None:
            return
        name = value.strip() or None
        if name and len(name) > 40:
            self.status.set("Use um nome de até 40 caracteres.")
            return
        try:
            self.device_store.rename(saved.address, name)
        except sqlite3.Error as error:
            self.status.set(f"Não foi possível renomear a fita: {error}")
            return
        self.saved_devices[target.label] = replace(saved, name=name)
        self.populate_devices(target.label)
        self.status.set(
            f"Nome alterado para {name}." if name else "Nome Bluetooth restaurado."
        )

    def forget_device(self):
        target = self.selected()
        if target is None or target.label in self.connections:
            return
        saved = self.saved_devices.get(target.label)
        if saved is None:
            return
        try:
            self.device_store.forget(saved.address)
        except sqlite3.Error as error:
            self.status.set(f"Não foi possível esquecer a fita: {error}")
            return
        self.saved_devices.pop(target.label)
        if isinstance(target, SavedDevice):
            self.targets.remove(target)
        self.populate_devices(target.label)
        self.status.set("Fita removida da lista.")

    def active_connections(self):
        label = self.control_target.get()
        if label == ALL_TARGETS and len(self.connections) > 1:
            return list(self.connections.items())
        if label in self.connections:
            return [(label, self.connections[label])]
        return []

    def handle_disconnects(self):
        while not self.lost_connections.empty():
            saved, connection, profile, callback = self.lost_connections.get()
            label = saved.label
            if self.connections.get(label) is not connection:
                continue
            self.connections.pop(label)
            self.playing = False
            self.reconnecting = True
            self.connecting = connection
            others = tuple(self.connections.values())
            name = self.short_device_name(label)

            async def recover():
                import asyncio

                await asyncio.gather(
                    *(item.stop() for item in others), return_exceptions=True
                )
                await connection.reconnect(saved, profile, callback)

            def recovered(_, error):
                self.connecting = None
                self.reconnecting = False
                if error:
                    self.animation_request = None
                    self.status.set(f"Sem conexão com {name}. {error}")
                else:
                    self.connections[label] = connection
                    self.status.set(f"{name} reconectada.")

            self.operation(recover(), f"Reconectando a {name}…", recovered)
            return
        if self.animation_request and not self.playing:
            labels, values, action = self.animation_request
            if all(label in self.connections for label in labels):
                self.start_animation(
                    [(label, self.connections[label]) for label in labels],
                    values,
                    action=action,
                    resumed=True,
                )

    def operation(self, coroutine, message, done, *, sending=False):
        self.busy = True
        self.sending = sending
        self.status.set(message)
        self.refresh()

        def finish(result, error):
            if self.closing:
                return
            self.busy = False
            self.sending = False
            done(result, error)
            self.refresh()
            action, self.deferred_action = self.deferred_action, None
            if action is not None and self.lost_connections.empty():
                action()
            self.schedule_slider_flush()

        self.pending = self.submit(coroutine, finish)

    def scan(self):
        from ..ble import transport

        if self.busy:
            if self.sending:
                self.deferred_action = self.scan
            return

        def finished(targets, error):
            if error:
                self.status.set(error)
                return
            selected = self.selected()
            retained = dict(self.saved_devices)
            retained.update(
                (target.label, target)
                for target in self.targets
                if target.label in self.connections
            )
            retained.update((target.label, target) for target in targets)
            self.targets = sorted(retained.values(), key=lambda target: target.label)
            self.populate_devices(selected.label if selected else None)
            self.status.set(
                "Escolha uma fita e clique em Conectar."
                if self.targets
                else "Nenhuma fita encontrada. Confira se a fita está com energia."
            )

        self.operation(transport.discover(), "Buscando fitas Bluetooth…", finished)

    def toggle_connection(self, *, on_success=None):
        target = self.selected()
        if target is None:
            return
        label = target.label
        if self.busy:
            if self.sending:

                def connect_selected():
                    if self.selected() and self.selected().label == label:
                        self.toggle_connection(on_success=on_success)

                self.deferred_action = connect_selected
            return
        if label in self.connections:
            connection = self.connections[label]
            animation_labels = (
                self.animation_request[0] if self.animation_request else ()
            )
            stop_animation = label in animation_labels
            animation_connections = tuple(
                self.connections[key]
                for key in animation_labels
                if key in self.connections
            )
            if stop_animation:
                self.animation_request = None
                self.playing = False

            async def disconnect():
                import asyncio

                if stop_animation:
                    await asyncio.gather(
                        *(item.stop() for item in animation_connections)
                    )
                await connection.disconnect()

            def disconnected(_, error):
                self.connections.pop(label, None)
                self.status.set(
                    error or f"{self.short_device_name(label)} desconectada."
                )

            self.operation(disconnect(), "Desconectando…", disconnected)
            return
        if len(self.connections) >= MAX_CONNECTIONS:
            return
        variant = self.variant.get() if target.model == protocol.BLEDOM else None
        profile = (
            protocol.BLEDOB_PROFILE
            if variant is None
            else protocol.BLEDOM_PROFILES[variant]
        )
        address = (
            target.address if isinstance(target, SavedDevice) else target.device.address
        )
        previous = self.saved_devices.get(label)
        saved = SavedDevice(
            address, target.model, variant, previous.name if previous else None
        )
        from ..control.session import DesktopConnection

        connection = DesktopConnection()
        self.connecting = connection

        def connected(_, error):
            self.connecting = None
            if error:
                self.status.set(error)
                return
            self.connections[label] = connection
            self.last_device_address = saved.address
            message = f"{self.short_device_name(label)} conectada."
            if on_success:
                on_success(message)
            try:
                self.device_store.remember(saved)
            except sqlite3.Error as store_error:
                self.status.set(
                    f"Fita conectada. Não foi possível salvar na lista: {store_error}"
                )
                return
            self.saved_devices[label] = saved
            self.populate_devices(label)
            self.status.set(message)

        def lost():
            self.lost_connections.put((saved, connection, profile, lost))

        self.operation(
            connection.connect(target, profile, lost), "Conectando à fita…", connected
        )

    def command(self, action, *values, on_success=None):
        targets = tuple(self.active_connections())
        if not targets:
            return
        if action == "cor":
            try:
                protocol.parse_rgb(values[0])
            except ValueError as error:
                self.status.set(str(error))
                return

        if self.busy:
            if self.sending:
                self.defer_for_targets(
                    targets,
                    lambda: self.command(action, *values, on_success=on_success),
                )
            return

        animation_labels = self.animation_request[0] if self.animation_request else ()
        stops_animation = action in MODE_COMMANDS and any(
            label in animation_labels for label, _ in targets
        )
        animation_connections = ()
        if stops_animation:
            animation_connections = tuple(
                self.connections[label]
                for label in animation_labels
                if label in self.connections
            )
            self.animation_request = None
            self.playing = False

        async def send():
            import asyncio

            from ..control.session import command_group

            if action == "desligar":
                for connection in animation_connections:
                    connection.cancel_animation()
            elif animation_connections:
                await asyncio.gather(
                    *(connection.stop() for connection in animation_connections)
                )
            await command_group(targets, action, list(values))

        def finished(_, error):
            message = (
                "Comando enviado."
                if len(targets) == 1
                else f"Comando enviado a {len(targets)} fitas."
            )
            if stops_animation:
                message = f"Reprodução interrompida. {message}"
            self.status.set(error or message)
            if not error and on_success:
                match action:
                    case "ligar":
                        notification = "Comando para ligar enviado."
                    case "desligar":
                        notification = "Comando para desligar enviado."
                    case "efeito":
                        notification = f"Efeito enviado: {EFFECT_LABELS[values[0]]}."
                    case "cor":
                        notification = f"Cor enviada: {values[0]}."
                    case _:
                        notification = message
                on_success(notification)

        message = "Desligando…" if action == "desligar" else "Enviando comando…"
        self.operation(send(), message, finished, sending=True)

    def toggle_animation(self, *, action="gradiente", use_last=False, on_success=None):
        if self.sending:
            self.defer_for_targets(
                tuple(self.active_connections()),
                lambda: self.toggle_animation(
                    action=action, use_last=use_last, on_success=on_success
                ),
            )
            return
        if self.animation_request and self.animation_request[2] == action:
            self.stop_animation(on_success=on_success)
            return
        targets = self.active_connections()
        if self.busy or not targets:
            return
        values = self.last_animation_values.get(action) if use_last else None
        self.start_animation(
            targets,
            values or self.animation_editor(action).values(),
            action=action,
            on_success=on_success,
        )

    def defer_for_targets(self, targets, callback):
        def run():
            if tuple(self.active_connections()) == targets:
                callback()

        self.deferred_action = run

    def start_animation(
        self, targets, values, *, action="gradiente", resumed=False, on_success=None
    ):
        previous = self.animation_request if self.playing else None
        request = (tuple(label for label, _ in targets), values, action)
        self.animation_request = request
        self.playing = True
        name = "Sequência" if action == "sequencia" else "Gradiente"
        self.status.set(
            f"{name}: voltando ao início…"
            if resumed
            else f"Reproduzindo: {name.lower()}…"
        )
        self.refresh()

        def finished(_, error):
            if (
                self.closing
                or self.animation_request is not request
                or not self.lost_connections.empty()
            ):
                return
            self.playing = False
            self.animation_request = None
            if error or not self.busy:
                self.status.set(error or "Reprodução concluída.")
            self.refresh()

        def started():
            if self.animation_request is request:
                self.last_animation_values[action] = values
                if on_success:
                    on_success(
                        "Sequência iniciada."
                        if action == "sequencia"
                        else "Gradiente iniciado."
                    )

        previous_connections = (
            [
                self.connections[label]
                for label in previous[0]
                if label in self.connections
            ]
            if previous
            else []
        )

        async def play():
            import asyncio

            from ..control.session import command_group

            if previous_connections:
                await asyncio.gather(
                    *(connection.stop() for connection in previous_connections)
                )
            if self.animation_request is request:
                await command_group(targets, action, values, on_started=started)

        self.submit(play(), finished)

    def stop_animation(self, *, on_success=None):
        action = self.animation_request[2] if self.animation_request else None
        self.animation_request = None
        if self.reconnecting:
            self.refresh()
            if on_success:
                on_success("Retomada cancelada.")
            return
        connections = tuple(self.connections.values())

        async def stop_all():
            import asyncio

            await asyncio.gather(*(connection.stop() for connection in connections))

        def stopped(_, error):
            self.playing = False
            self.status.set(error or "Reprodução parada.")
            if not error and on_success:
                on_success(
                    "Sequência parada."
                    if action == "sequencia"
                    else "Gradiente parado."
                )

        self.operation(stop_all(), "Parando a reprodução…", stopped)

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.connection_progress.stop()
        if self.brightness_save_job is not None:
            self.root.after_cancel(self.brightness_save_job)
        self.save_brightness()
        if self.slider_timer is not None:
            self.root.after_cancel(self.slider_timer)
        for editor in self.animation_editors.values():
            editor.cancel_pending()
        self.palette.cancel_pending()
        if self.pending is not None:
            self.pending.cancel()
        if self.loop is None:
            self.destroyed = True
            self.root.destroy()
            return
        self.root.withdraw()

        def closed(_, __):
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.destroyed = True
            self.root.destroy()

        connections = tuple(self.connections.values())
        if self.connecting is not None:
            connections += (self.connecting,)

        async def disconnect_all():
            import asyncio

            await asyncio.gather(
                *(connection.disconnect() for connection in connections),
                return_exceptions=True,
            )

        self.submit(disconnect_all(), closed)
