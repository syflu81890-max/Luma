"""Explicit, non-forcing power actions; never imported for side effects."""
import os,subprocess,sys

def sleep_windows():
    import ctypes
    from ctypes import wintypes as w
    class LUID(ctypes.Structure):_fields_=[('LowPart',w.DWORD),('HighPart',w.LONG)]
    class TOKEN_PRIVILEGES(ctypes.Structure):_fields_=[('PrivilegeCount',w.DWORD),('Luid',LUID),('Attributes',w.DWORD)]
    adv=ctypes.WinDLL('advapi32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True);power=ctypes.WinDLL('powrprof',use_last_error=True)
    kernel.GetCurrentProcess.restype=w.HANDLE;kernel.CloseHandle.argtypes=[w.HANDLE]
    adv.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)];adv.OpenProcessToken.restype=w.BOOL
    adv.LookupPrivilegeValueW.argtypes=[w.LPCWSTR,w.LPCWSTR,ctypes.POINTER(LUID)];adv.LookupPrivilegeValueW.restype=w.BOOL
    adv.AdjustTokenPrivileges.argtypes=[w.HANDLE,w.BOOL,ctypes.POINTER(TOKEN_PRIVILEGES),w.DWORD,ctypes.c_void_p,ctypes.c_void_p];adv.AdjustTokenPrivileges.restype=w.BOOL
    power.SetSuspendState.argtypes=[ctypes.c_ubyte,ctypes.c_ubyte,ctypes.c_ubyte];power.SetSuspendState.restype=ctypes.c_ubyte
    token=w.HANDLE()
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(),0x20|0x8,ctypes.byref(token)):raise ctypes.WinError(ctypes.get_last_error())
    try:
        privileges=TOKEN_PRIVILEGES();privileges.PrivilegeCount=1;privileges.Attributes=2
        if not adv.LookupPrivilegeValueW(None,'SeShutdownPrivilege',ctypes.byref(privileges.Luid)):raise ctypes.WinError(ctypes.get_last_error())
        ctypes.set_last_error(0)
        if not adv.AdjustTokenPrivileges(token,False,ctypes.byref(privileges),0,None,None) or ctypes.get_last_error():raise ctypes.WinError(ctypes.get_last_error())
        if not power.SetSuspendState(False,False,False):raise ctypes.WinError(ctypes.get_last_error())
    finally:kernel.CloseHandle(token)

def execute(action):
    if os.name!='nt':raise RuntimeError('完成后动作仅支持 Windows')
    if action=='shutdown':
        # /t > 0 implicitly forces applications closed. Count down inside Luma instead.
        subprocess.run([os.path.join(os.environ.get('SystemRoot',r'C:\Windows'),'System32','shutdown.exe'),'/s','/t','0'],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),capture_output=True)
    elif action=='sleep':sleep_windows()
    else:raise ValueError('未知电源动作')

if __name__=='__main__':execute(sys.argv[1])
