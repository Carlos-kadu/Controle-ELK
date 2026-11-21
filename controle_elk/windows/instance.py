import ctypes
from contextlib import contextmanager
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183


def kernel_api():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateEventW": (
            [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR],
            wintypes.HANDLE,
        ),
        "CreateMutexW": (
            [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR],
            wintypes.HANDLE,
        ),
        "SetEvent": ([wintypes.HANDLE], wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (parameters, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes = parameters
        function.restype = result
    return kernel


@contextmanager
def desktop_instance(*, request_restore, name=r"Local\ControleELK.Desktop"):
    kernel = kernel_api()
    event = kernel.CreateEventW(None, False, False, name + ".Restore")
    if not event:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        mutex = kernel.CreateMutexW(None, False, name + ".Instance")
        error = ctypes.get_last_error()
        if not mutex:
            raise ctypes.WinError(error)
        try:
            if error == ERROR_ALREADY_EXISTS:
                if request_restore:
                    kernel.SetEvent(event)
                yield None
            else:
                yield lambda: kernel.WaitForSingleObject(event, 0) == 0
        finally:
            kernel.CloseHandle(mutex)
    finally:
        kernel.CloseHandle(event)
