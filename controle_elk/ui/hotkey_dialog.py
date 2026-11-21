import tkinter as tk
from tkinter import ttk

from ..windows import hotkeys
from .desktop import EFFECT_BY_LABEL, EFFECT_LABELS, PRESETS
from .dialogs import use_dark_title_bar
from .theme import DISABLED, MUTED, PANEL, TEXT

NO_KEY = "Nenhuma"


class HotkeyDialog(tk.Toplevel):
    def __init__(self, view, tray):
        super().__init__(view.root)
        self.title("Atalhos do teclado")
        self.transient(view.root)
        self.resizable(False, False)
        self.configure(bg=PANEL)
        self.bind("<Escape>", self.dismiss)
        self.protocol("WM_DELETE_WINDOW", self.dismiss)
        self.tray = tray
        enabled, shortcuts, options = tray.hotkey_config
        self.enabled = tk.BooleanVar(self, value=enabled)
        self.status = tk.StringVar(self)
        self.effect = tk.StringVar(self, value=EFFECT_LABELS[options["efeito"]])
        self.color = tk.StringVar(self, value=options["cor"])
        self.show_notice = tk.BooleanVar(self, value=options["mostrar_aviso"])
        self.fields = {}
        self.rows = {}
        self.option_boxes = {}
        content = view.panel(self)
        content.pack(fill="both", expand=True)
        ttk.Checkbutton(
            content,
            text="Ativar atalhos globais",
            variable=self.enabled,
            command=self.refresh_rows,
            cursor="hand2",
        ).grid(row=0, columnspan=4, sticky="w")
        view.label(
            content, "Escolha Nenhuma para desativar um atalho.", color=MUTED
        ).grid(row=1, columnspan=4, sticky="w", pady=(4, 12))
        for row, (action, label) in enumerate(hotkeys.ACTIONS.items(), 2):
            modifier, key = shortcuts[action]
            modifier_var = tk.StringVar(self, value=modifier)
            key_var = tk.StringVar(self, value=key or NO_KEY)
            self.fields[action] = modifier_var, key_var
            caption = view.label(content, label)
            caption.grid(row=row, column=0, sticky="w", padx=(0, 12))
            modifier_box = ttk.Combobox(
                content,
                textvariable=modifier_var,
                values=tuple(hotkeys.MODIFIERS),
                state="readonly",
                width=21,
            )
            modifier_box.grid(row=row, column=1, sticky="ew", pady=3)
            key_box = ttk.Combobox(
                content,
                textvariable=key_var,
                values=(NO_KEY, *hotkeys.KEYS),
                state="readonly",
                width=9,
            )
            key_box.grid(row=row, column=2, sticky="ew", padx=(5, 0))
            key_box.bind("<<ComboboxSelected>>", lambda _: self.refresh_rows())
            self.rows[action] = caption, modifier_box, key_box
            if action == "efeito":
                self.option_boxes[action] = ttk.Combobox(
                    content,
                    textvariable=self.effect,
                    values=tuple(EFFECT_BY_LABEL),
                    state="readonly",
                    width=28,
                )
            elif action == "cor":
                self.option_boxes[action] = ttk.Combobox(
                    content,
                    textvariable=self.color,
                    values=PRESETS,
                    width=28,
                )
            if action in self.option_boxes:
                self.option_boxes[action].grid(
                    row=row, column=3, sticky="ew", padx=(8, 0)
                )
        footer = len(hotkeys.ACTIONS) + 2
        ttk.Checkbutton(
            content,
            text="Mostrar confirmação na tela",
            variable=self.show_notice,
            cursor="hand2",
        ).grid(row=footer, columnspan=4, sticky="w", pady=(8, 0))
        view.label(content, variable=self.status, color=MUTED).grid(
            row=footer + 1, columnspan=4, sticky="w", pady=(8, 0)
        )
        self.save_button = view.button(content, "Salvar", self.save, primary=True)
        self.save_button.grid(row=footer + 2, columnspan=4, sticky="e", pady=(8, 0))
        self.reset_button = view.button(
            content, "Restaurar padrão", self.restore_defaults
        )
        self.reset_button.grid(row=footer + 2, columnspan=3, sticky="w", pady=(8, 0))
        self.refresh_rows()
        self.update_idletasks()
        use_dark_title_bar(self)

    def dismiss(self, _=None):
        if self.save_button.instate(["!disabled"]):
            self.destroy()

    def refresh_rows(self):
        enabled = self.enabled.get()
        for action, (caption, modifier_box, key_box) in self.rows.items():
            active = enabled and self.fields[action][1].get() != NO_KEY
            caption.configure(fg=TEXT if active else DISABLED)
            modifier_box.configure(state="readonly" if active else "disabled")
            key_box.configure(
                state="readonly" if enabled else "disabled",
                style="TCombobox" if active else "Inactive.TCombobox",
            )
            if action in self.option_boxes:
                editable = "normal" if action == "cor" else "readonly"
                self.option_boxes[action].configure(
                    state=editable if active else "disabled"
                )

    def restore_defaults(self):
        _, shortcuts, options = hotkeys.default_config()
        for action, (modifier, key) in shortcuts.items():
            modifier_var, key_var = self.fields[action]
            modifier_var.set(modifier)
            key_var.set(key or NO_KEY)
        self.effect.set(EFFECT_LABELS[options["efeito"]])
        self.color.set(options["cor"])
        self.show_notice.set(options["mostrar_aviso"])
        self.refresh_rows()
        self.status.set("Padrão restaurado. Clique em Salvar para aplicar.")

    def save(self):
        try:
            shortcuts = {
                action: (modifier.get(), "" if key.get() == NO_KEY else key.get())
                for action, (modifier, key) in self.fields.items()
            }
            options = hotkeys.shortcut_options(
                {
                    "efeito": EFFECT_BY_LABEL[self.effect.get()],
                    "cor": self.color.get(),
                    "mostrar_aviso": self.show_notice.get(),
                }
            )
            config = self.enabled.get(), shortcuts, options
            hotkeys.bindings(config)
            self.tray.request_hotkeys(config)
        except (OSError, ValueError) as error:
            self.status.set(str(error))
            return
        self.save_button.state(["disabled"])
        self.reset_button.state(["disabled"])
        self.status.set("Salvando…")

    def complete(self, error):
        if error:
            self.status.set(error)
            self.save_button.state(["!disabled"])
            self.reset_button.state(["!disabled"])
        else:
            self.destroy()
