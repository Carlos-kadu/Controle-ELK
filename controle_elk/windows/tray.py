import ctypes
import logging
import queue
import threading
from ctypes import wintypes as win
from pathlib import Path

from . import hotkeys, startup

ICON_PATH = Path(__file__).resolve().parents[1] / "ui" / "assets" / "controle-elk.ico"
WINDOW_CLASS = "ControleELK.Tray"
WM_TRAY = 0x8001
WM_UPDATE_HOTKEYS = 0x8002
WM_HOTKEY = 0x0312
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_CONTEXTMENU = 0x007B
WM_TIMER = 0x0113
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
NIN_SELECT = 0x0400
NIN_KEYSELECT = 0x0401
NIM_ADD, NIM_DELETE, NIM_SETFOCUS, NIM_SETVERSION = 0, 2, 3, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_SHOWTIP = 1, 2, 4, 0x80
MF_CHECKED, MF_SEPARATOR = 8, 0x0800
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 2, 0x0080, 0x0100
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
MENU = {
    1: ("show", "Abrir Controle ELK"),
    2: ("hide", "Ocultar na bandeja"),
    3: ("startup", "Iniciar com o Windows"),
    4: ("exit", "Sair"),
    5: ("hotkey_settings", "Atalhos do teclado…"),
}
HOTKEY_IDS = {action: number for number, action in enumerate(hotkeys.ACTIONS, 1)}

log = logging.getLogger(__name__)

LRESULT = ctypes.c_ssize_t
UINT_PTR = ctypes.c_size_t
WindowProc = ctypes.WINFUNCTYPE(LRESULT, win.HWND, win.UINT, win.WPARAM, win.LPARAM)


class WindowClass(ctypes.Structure):
    _fields_ = [
        ("style", win.UINT),
        ("procedure", WindowProc),
        ("class_extra", ctypes.c_int),
        ("window_extra", ctypes.c_int),
        ("instance", win.HINSTANCE),
        ("icon", win.HICON),
        ("cursor", win.HANDLE),
        ("background", win.HBRUSH),
        ("menu_name", win.LPCWSTR),
        ("class_name", win.LPCWSTR),
    ]


class NotifyIconData(ctypes.Structure):
    _fields_ = [
        ("size", win.DWORD),
        ("window", win.HWND),
        ("id", win.UINT),
        ("flags", win.UINT),
        ("callback", win.UINT),
        ("icon", win.HICON),
        ("tip", win.WCHAR * 128),
        ("state", win.DWORD),
        ("state_mask", win.DWORD),
        ("info", win.WCHAR * 256),
        ("version", win.UINT),
        ("info_title", win.WCHAR * 64),
        ("info_flags", win.DWORD),
        ("guid", win.DWORD * 4),
        ("balloon_icon", win.HICON),
    ]


def native_library(name, signatures):
    library = ctypes.WinDLL(name, use_last_error=True)
    for name, (result, args) in signatures.items():
        function = getattr(library, name)
        function.restype = result
        function.argtypes = args
    return library


class Tray:
    def __init__(self):
        self.events = queue.SimpleQueue()
        self.hotkey_requests = queue.SimpleQueue()
        self.hotkey_config = hotkeys.load_config()
        self.registered_hotkeys = {}
        self.ready = threading.Event()
        self.failed = threading.Event()
        self.stopping = threading.Event()
        self.window = None
        self.data = None
        self.version4 = False
        self.attempts = 0
        try:
            self.startup_enabled = startup.enabled()
        except OSError:
            self.startup_enabled = False
        self.thread = threading.Thread(target=self.run, name="elk-tray", daemon=True)
        self.thread.start()

    def init_api(self):
        window_message = (win.HWND, win.UINT, win.WPARAM, win.LPARAM)
        message = ctypes.POINTER(win.MSG)
        self.user = native_library(
            "user32",
            {
                "RegisterClassW": (win.ATOM, (ctypes.POINTER(WindowClass),)),
                "UnregisterClassW": (win.BOOL, (win.LPCWSTR, win.HINSTANCE)),
                "RegisterWindowMessageW": (win.UINT, (win.LPCWSTR,)),
                "CreateWindowExW": (
                    win.HWND,
                    (
                        win.DWORD,
                        win.LPCWSTR,
                        win.LPCWSTR,
                        win.DWORD,
                        ctypes.c_int,
                        ctypes.c_int,
                        ctypes.c_int,
                        ctypes.c_int,
                        win.HWND,
                        win.HMENU,
                        win.HINSTANCE,
                        win.LPVOID,
                    ),
                ),
                "DefWindowProcW": (LRESULT, window_message),
                "PostMessageW": (win.BOOL, window_message),
                "PostQuitMessage": (None, (ctypes.c_int,)),
                "GetMessageW": (win.BOOL, (message, win.HWND, win.UINT, win.UINT)),
                "TranslateMessage": (win.BOOL, (message,)),
                "DispatchMessageW": (LRESULT, (message,)),
                "DestroyWindow": (win.BOOL, (win.HWND,)),
                "LoadImageW": (
                    win.HANDLE,
                    (
                        win.HINSTANCE,
                        win.LPCWSTR,
                        win.UINT,
                        ctypes.c_int,
                        ctypes.c_int,
                        win.UINT,
                    ),
                ),
                "DestroyIcon": (win.BOOL, (win.HICON,)),
                "CreatePopupMenu": (win.HMENU, ()),
                "RegisterHotKey": (
                    win.BOOL,
                    (win.HWND, ctypes.c_int, win.UINT, win.UINT),
                ),
                "UnregisterHotKey": (win.BOOL, (win.HWND, ctypes.c_int)),
                "AppendMenuW": (win.BOOL, (win.HMENU, win.UINT, UINT_PTR, win.LPCWSTR)),
                "DestroyMenu": (win.BOOL, (win.HMENU,)),
                "SetForegroundWindow": (win.BOOL, (win.HWND,)),
                "GetCursorPos": (win.BOOL, (ctypes.POINTER(win.POINT),)),
                "TrackPopupMenu": (
                    win.UINT,
                    (
                        win.HMENU,
                        win.UINT,
                        ctypes.c_int,
                        ctypes.c_int,
                        ctypes.c_int,
                        win.HWND,
                        win.LPVOID,
                    ),
                ),
                "SetTimer": (UINT_PTR, (win.HWND, UINT_PTR, win.UINT, win.LPVOID)),
                "KillTimer": (win.BOOL, (win.HWND, UINT_PTR)),
            },
        )
        kernel = native_library(
            "kernel32",
            {
                "GetModuleHandleW": (win.HMODULE, (win.LPCWSTR,)),
            },
        )
        self.instance = kernel.GetModuleHandleW(None)
        self.shell = native_library(
            "shell32",
            {
                "Shell_NotifyIconW": (
                    win.BOOL,
                    (win.DWORD, ctypes.POINTER(NotifyIconData)),
                ),
            },
        )

    def notify(self, action):
        return self.shell.Shell_NotifyIconW(action, ctypes.byref(self.data))

    def add_icon(self):
        self.ready.clear()
        if self.notify(NIM_ADD):
            self.version4 = bool(self.notify(NIM_SETVERSION))
            self.user.KillTimer(self.window, 1)
            self.failed.clear()
            self.ready.set()
        elif self.attempts < 6 and self.user.SetTimer(self.window, 1, 500, None):
            self.attempts += 1
        else:
            self.user.KillTimer(self.window, 1)
            self.failed.set()

    def show_menu(self, window, position=None):
        menu = self.user.CreatePopupMenu()
        if not menu:
            return
        try:
            for item in (1, 2, 5, 3, 4):
                _, title = MENU[item]
                if item == 3:
                    self.user.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                flags = MF_CHECKED if item == 3 and self.startup_enabled else 0
                self.user.AppendMenuW(menu, flags, item, title)
            if position is None:
                point = win.POINT()
                if not self.user.GetCursorPos(ctypes.byref(point)):
                    return
                position = point.x, point.y
            self.user.SetForegroundWindow(window)
            item = self.user.TrackPopupMenu(
                menu,
                TPM_RIGHTBUTTON | TPM_NONOTIFY | TPM_RETURNCMD,
                *position,
                0,
                window,
                None,
            )
            if item in MENU:
                self.events.put(MENU[item][0])
            else:
                self.notify(NIM_SETFOCUS)
            self.user.PostMessageW(window, 0, 0, 0)
        finally:
            self.user.DestroyMenu(menu)

    def request_hotkeys(self, config):
        self.hotkey_requests.put(config)
        if not self.window or not self.user.PostMessageW(
            self.window, WM_UPDATE_HOTKEYS, 0, 0
        ):
            self.hotkey_requests.get_nowait()
            raise OSError("Os atalhos do Windows não estão disponíveis.")

    def register_hotkeys(self, desired):
        for action, binding in tuple(self.registered_hotkeys.items()):
            if desired.get(action) != binding:
                self.user.UnregisterHotKey(self.window, HOTKEY_IDS[action])
                del self.registered_hotkeys[action]
        unavailable = []
        for action, binding in desired.items():
            if action in self.registered_hotkeys:
                continue
            if self.user.RegisterHotKey(self.window, HOTKEY_IDS[action], *binding):
                self.registered_hotkeys[action] = binding
            else:
                unavailable.append(hotkeys.ACTIONS[action])
        return unavailable

    def update_hotkeys(self):
        try:
            config = self.hotkey_requests.get_nowait()
        except queue.Empty:
            return
        previous = self.registered_hotkeys.copy()
        try:
            unavailable = self.register_hotkeys(hotkeys.bindings(config))
            if unavailable:
                raise ValueError(
                    "Combinação indisponível para: " + ", ".join(unavailable)
                )
            hotkeys.save_config(config)
        except (ValueError, OSError) as error:
            self.register_hotkeys(previous)
            self.events.put(("hotkey_result", str(error)))
        else:
            self.hotkey_config = config
            self.events.put(("hotkey_result", None))

    def dispatch(self, window, message, wparam, lparam):
        if message == WM_UPDATE_HOTKEYS:
            self.update_hotkeys()
            return 0
        if message == WM_HOTKEY:
            for action, binding in self.registered_hotkeys.items():
                modifiers, key = binding
                if wparam == HOTKEY_IDS[action] and lparam & 0xFFFF000F == (
                    (key << 16) | (modifiers & 15)
                ):
                    self.events.put(("hotkey", action))
                    break
            return 0
        if message == WM_DESTROY:
            self.register_hotkeys({})
            if self.data is not None:
                self.notify(NIM_DELETE)
            self.window = None
            self.user.PostQuitMessage(0)
            return 0
        if self.data is not None:
            if message == self.taskbar_created:
                self.attempts = 0
                self.add_icon()
                return 0
            if message == WM_TIMER and wparam == 1:
                self.add_icon()
                return 0
            if message == WM_TRAY:
                event = lparam & 0xFFFF
                if event in (NIN_SELECT, NIN_KEYSELECT) or (
                    not self.version4 and event == WM_LBUTTONUP
                ):
                    self.events.put("show")
                elif event == WM_CONTEXTMENU and self.version4:
                    position = (
                        ctypes.c_short(wparam & 0xFFFF).value,
                        ctypes.c_short((wparam >> 16) & 0xFFFF).value,
                    )
                    self.show_menu(window, position)
                elif not self.version4 and event == WM_RBUTTONUP:
                    self.show_menu(window)
                return 0
        return self.user.DefWindowProcW(window, message, wparam, lparam)

    def run(self):
        registered = False
        icon = None
        try:
            self.init_api()
            self.taskbar_created = self.user.RegisterWindowMessageW("TaskbarCreated")
            self.procedure = WindowProc(self.dispatch)
            window_class = WindowClass(
                procedure=self.procedure,
                instance=self.instance,
                class_name=WINDOW_CLASS,
            )
            registered = self.user.RegisterClassW(ctypes.byref(window_class))
            if not registered:
                raise ctypes.WinError(ctypes.get_last_error())
            self.window = self.user.CreateWindowExW(
                0,
                WINDOW_CLASS,
                WINDOW_CLASS,
                0,
                0,
                0,
                0,
                0,
                None,
                None,
                self.instance,
                None,
            )
            if not self.window:
                raise ctypes.WinError(ctypes.get_last_error())
            if self.stopping.is_set():
                return
            unavailable = self.register_hotkeys(hotkeys.bindings(self.hotkey_config))
            if unavailable:
                self.events.put(
                    (
                        "hotkey_status",
                        "Atalhos indisponíveis: " + ", ".join(unavailable),
                    )
                )
            icon = self.user.LoadImageW(
                None, str(ICON_PATH), IMAGE_ICON, 0, 0, LR_LOADFROMFILE
            )
            if not icon:
                raise ctypes.WinError(ctypes.get_last_error())
            self.data = NotifyIconData(
                size=ctypes.sizeof(NotifyIconData),
                window=self.window,
                id=1,
                flags=NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP,
                callback=WM_TRAY,
                icon=icon,
                tip="Controle de fitas ELK",
                version=4,
            )
            self.add_icon()
            message = win.MSG()
            while (
                received := self.user.GetMessageW(ctypes.byref(message), None, 0, 0)
            ) > 0:
                self.user.TranslateMessage(ctypes.byref(message))
                self.user.DispatchMessageW(ctypes.byref(message))
            if received < 0:
                raise ctypes.WinError(ctypes.get_last_error())
        except (OSError, AttributeError):
            self.failed.set()
            log.exception("Falha ao abrir a bandeja do Windows.")
        finally:
            self.ready.clear()
            if self.window:
                self.user.DestroyWindow(self.window)
            if icon:
                self.user.DestroyIcon(icon)
            if registered:
                self.user.UnregisterClassW(WINDOW_CLASS, self.instance)

    def toggle_startup(self):
        self.startup_enabled = startup.toggle()
        return self.startup_enabled

    def stop(self):
        self.stopping.set()
        if self.window:
            self.user.PostMessageW(self.window, WM_CLOSE, 0, 0)
        self.thread.join(timeout=2)
