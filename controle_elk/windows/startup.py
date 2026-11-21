import sys
import winreg
from pathlib import Path
from subprocess import list2cmdline

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "ControleELK"


def enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except FileNotFoundError:
        return False


def command_line():
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        arguments = [str(executable)]
    else:
        pythonw = executable.with_name("pythonw.exe")
        interpreter = pythonw if pythonw.is_file() else executable
        arguments = [str(interpreter), "-m", "controle_elk", "interface"]
    return list2cmdline([*arguments, "--minimizado"])


def toggle():
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        RUN_KEY,
        0,
        winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
    ) as key:
        try:
            winreg.QueryValueEx(key, APP_NAME)
        except FileNotFoundError:
            command = command_line()
            if len(command) > 260:
                raise OSError(
                    "Mova o aplicativo para um caminho mais curto para iniciar com o Windows."
                )
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            return True
        winreg.DeleteValue(key, APP_NAME)
        return False
