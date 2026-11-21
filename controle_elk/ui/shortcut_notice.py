import ctypes
import tkinter as tk
from ctypes import wintypes

from .theme import BORDER, CONNECTED_GREEN, PANEL, TEXT

DISPLAY_MS = 1500
MARGIN = 16
SPI_GETWORKAREA = 0x0030
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


class ShortcutNotice:
    def __init__(self, root):
        self.root = root
        self.window = None
        self.timer = None

    def show(self, message):
        self.dismiss()
        window = tk.Toplevel(self.root)
        self.window = window
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=BORDER, padx=1, pady=1)
        label = tk.Label(
            window,
            text=f"●  {message}",
            bg=PANEL,
            fg=TEXT,
            highlightthickness=1,
            highlightbackground=CONNECTED_GREEN,
            font=("Segoe UI", 10),
            padx=14,
            pady=10,
            justify="left",
            wraplength=330,
        )
        label.pack(fill="both", expand=True)

        window.update_idletasks()
        user = ctypes.windll.user32
        frame = wintypes.HWND(int(str(window.wm_frame()), 0))
        style = user.GetWindowLongW(frame, GWL_EXSTYLE)
        user.SetWindowLongW(
            frame, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        )
        area = wintypes.RECT()
        if user.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(area), 0):
            right, bottom = area.right, area.bottom
        else:
            right, bottom = window.winfo_screenwidth(), window.winfo_screenheight()
        x = right - window.winfo_reqwidth() - MARGIN
        y = bottom - window.winfo_reqheight() - MARGIN
        window.geometry(f"{x:+d}{y:+d}")
        window.deiconify()
        self.timer = self.root.after(DISPLAY_MS, self.dismiss)

    def dismiss(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        if self.window is not None:
            self.window.destroy()
            self.window = None
