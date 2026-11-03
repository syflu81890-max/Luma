"""Native CF_HDROP clipboard support for copying one or more original files."""
import ctypes,struct,time
from ctypes import wintypes
def copy_files(paths):
    if not paths:raise ValueError('没有可复制的文件')
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GlobalAlloc.argtypes=[wintypes.UINT,ctypes.c_size_t];kernel.GlobalAlloc.restype=wintypes.HGLOBAL
    kernel.GlobalLock.argtypes=[wintypes.HGLOBAL];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[wintypes.HGLOBAL];kernel.GlobalFree.argtypes=[wintypes.HGLOBAL]
    user.SetClipboardData.argtypes=[wintypes.UINT,wintypes.HANDLE];user.SetClipboardData.restype=wintypes.HANDLE
    payload=struct.pack('<IiiII',20,0,0,0,1)+('\0'.join(paths)+'\0\0').encode('utf-16le');handle=kernel.GlobalAlloc(0x42,len(payload));ptr=kernel.GlobalLock(handle)
    if not ptr:raise OSError('无法创建剪贴板内容')
    ctypes.memmove(ptr,payload,len(payload));kernel.GlobalUnlock(handle)
    opened=False
    try:
        for _ in range(10):
            if user.OpenClipboard(None):opened=True;break
            time.sleep(.05)
        if not opened:raise OSError('剪贴板正忙，请稍后再试')
        user.EmptyClipboard()
        if not user.SetClipboardData(15,handle):raise OSError('复制文件失败')
        handle=None
    finally:
        if opened:user.CloseClipboard()
        if handle:kernel.GlobalFree(handle)
    return len(paths)
