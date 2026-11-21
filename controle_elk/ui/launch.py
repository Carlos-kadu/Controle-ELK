import argparse
import logging
import queue
import sys

from controle_elk.storage.paths import data_directory
from controle_elk.windows.instance import desktop_instance
from controle_elk.windows.tray import ICON_PATH, Tray

TRAY_UNAVAILABLE = "A bandeja do Windows não está disponível."


def startup_status(tray):
    try:
        enabled = tray.toggle_startup()
    except OSError as error:
        return f"Falha ao configurar início automático: {error}"
    return (
        "Início com o Windows ativado."
        if enabled
        else "Início com o Windows desativado."
    )


def wait_for_window(tray, restore_requested):
    status = None
    while not tray.failed.is_set():
        if restore_requested():
            return "show", status
        try:
            action = tray.events.get(timeout=0.24)
        except queue.Empty:
            continue
        if action in ("show", "hotkey_settings", ("hotkey", "conectar")):
            return action, status
        if action == "exit":
            return None, None
        if action == "startup":
            status = startup_status(tray)
        if isinstance(action, tuple) and action[0] == "hotkey_status":
            status = action[1]
    return "show", TRAY_UNAVAILABLE


class WindowHost:
    def __init__(self, root, tray, restore_requested, status=None, action="show"):
        from controle_elk.ui.desktop import Desktop
        from controle_elk.ui.dialogs import use_dark_title_bar
        from controle_elk.ui.shortcut_notice import ShortcutNotice

        self.root = root
        self.tray = tray
        self.restore_requested = restore_requested
        self.tray_failed = status == TRAY_UNAVAILABLE
        self.hotkey_dialog = None
        self.shortcut_notice = ShortcutNotice(root)
        self.app = Desktop(root, open_hotkeys=self.show_hotkey_settings)
        self.root.iconbitmap(default=str(ICON_PATH))
        self.root.protocol("WM_DELETE_WINDOW", self.hide_or_exit)
        self.root.bind("<Unmap>", self.on_unmap, add="+")
        self.root.update_idletasks()
        use_dark_title_bar(root)
        if status:
            self.app.status.set(status)
        if action == ("hotkey", "conectar"):
            self.run_hotkey("conectar")
        else:
            self.show()
            if action == "hotkey_settings":
                self.show_hotkey_settings()
        self.root.after(100, self.poll)

    def on_unmap(self, event):
        if (
            event.widget is self.root
            and self.root.state() == "iconic"
            and self.tray.ready.is_set()
        ):
            self.root.after_idle(self.hide_or_exit)

    def hide_or_exit(self):
        if self.app.closing:
            return
        if self.tray.ready.is_set() and not self.tray.failed.is_set():
            self.root.withdraw()
        else:
            self.app.close()

    def show(self):
        if self.app.closing:
            return
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def show_hotkey_settings(self):
        from controle_elk.ui.hotkey_dialog import HotkeyDialog

        if self.hotkey_dialog is None or not self.hotkey_dialog.winfo_exists():
            self.hotkey_dialog = HotkeyDialog(self.app, self.tray)
        self.hotkey_dialog.lift()
        self.hotkey_dialog.focus_set()

    def run_hotkey(self, action):
        def notify(message):
            self.tray.events.put(("shortcut_notice", message))

        match action:
            case "conectar":
                if not self.app.connect_last_device(on_success=notify):
                    self.show()
            case "ligar" | "desligar":
                self.app.command(action, on_success=notify)
            case "gradiente" | "sequencia":
                self.app.toggle_animation(
                    action=action, use_last=True, on_success=notify
                )
            case "efeito":
                self.app.activate_effect(
                    self.tray.hotkey_config[2]["efeito"], on_success=notify
                )
            case "cor":
                self.app.set_color(self.tray.hotkey_config[2]["cor"], on_success=notify)
            case "proxima_cor":
                self.app.next_preset_color(on_success=notify)

    def poll(self):
        if self.app.closing:
            return
        if self.restore_requested():
            self.show()
        failed = self.tray.failed.is_set()
        if failed and not self.tray_failed:
            self.app.status.set(TRAY_UNAVAILABLE)
            self.show()
        self.tray_failed = failed
        while not self.tray.events.empty():
            action = self.tray.events.get()
            match action:
                case "show":
                    self.show()
                case "hide":
                    self.hide_or_exit()
                case "startup":
                    self.app.status.set(startup_status(self.tray))
                case "hotkey_settings":
                    self.show()
                    self.show_hotkey_settings()
                case ("hotkey", command):
                    self.run_hotkey(command)
                case ("hotkey_status", message):
                    self.app.status.set(message)
                case ("shortcut_notice", message):
                    if self.tray.hotkey_config[2]["mostrar_aviso"]:
                        self.shortcut_notice.show(message)
                case ("hotkey_result", error):
                    if (
                        self.hotkey_dialog is not None
                        and self.hotkey_dialog.winfo_exists()
                    ):
                        self.hotkey_dialog.complete(error)
                    if error is None:
                        if not self.tray.hotkey_config[2]["mostrar_aviso"]:
                            self.shortcut_notice.dismiss()
                        self.app.status.set("Atalhos atualizados.")
                case "exit":
                    self.app.close()
                    return
        interval = 240 if self.root.state() == "withdrawn" else 100
        self.root.after(interval, self.poll)


def run_window(minimized, restore_requested):
    tray = Tray()
    try:
        status = None
        action = "show"
        if minimized:
            action, status = wait_for_window(tray, restore_requested)
            if action is None:
                return

        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        WindowHost(root, tray, restore_requested, status, action)
        root.mainloop()
    finally:
        tray.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Controle de fitas ELK para Windows.")
    parser.add_argument(
        "--minimizado", action="store_true", help="Inicia diretamente na bandeja."
    )
    args = parser.parse_args(argv)
    with desktop_instance(request_restore=not args.minimizado) as restore_requested:
        if restore_requested is None:
            return
        if getattr(sys, "frozen", False):
            folder = data_directory()
            folder.mkdir(parents=True, exist_ok=True)
            logging.basicConfig(
                filename=folder / "controle-elk.log",
                filemode="w",
                level=logging.WARNING,
            )
        try:
            run_window(args.minimizado, restore_requested)
        except Exception:
            logging.exception("Falha ao abrir o Controle ELK.")
            raise


if __name__ == "__main__":
    main()
