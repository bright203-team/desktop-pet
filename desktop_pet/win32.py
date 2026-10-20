"""All native Windows calls live here. Imported only by the Windows entry point."""
import time
import sys
import ctypes as C
from ctypes import wintypes as W
from .model import Target


def startup_folder():
    """Use the shell's actual current-user folder, including redirected folders."""
    if sys.platform != 'win32':
        raise OSError('Windows でのみ変更できます')
    shell = C.WinDLL('shell32', use_last_error=True)
    shell.SHGetFolderPathW.argtypes = [W.HWND, C.c_int, W.HANDLE, W.DWORD, W.LPWSTR]
    shell.SHGetFolderPathW.restype = C.c_long
    path = C.create_unicode_buffer(260)
    result = shell.SHGetFolderPathW(None, 0x0007, None, 0, path)  # CSIDL_STARTUP
    if result != 0 or not path.value:
        raise OSError('スタートアップのフォルダを取得できませんでした')
    return path.value

class Win32:
    def __init__(self):
        self.user = C.WinDLL('user32', use_last_error=True)
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.enum_proc = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        signatures = {
            'SetWinEventHook': ([W.DWORD,W.DWORD,W.HMODULE,C.c_void_p,W.DWORD,W.DWORD,W.DWORD],W.HANDLE),
            'UnhookWinEvent': ([W.HANDLE],W.BOOL),
            'EnumWindows': ([self.enum_proc,W.LPARAM],W.BOOL),
            'IsWindow': ([W.HWND],W.BOOL),
            'GetForegroundWindow': ([],W.HWND),
            'GetWindow': ([W.HWND,W.UINT],W.HWND),
            'IsWindowVisible': ([W.HWND],W.BOOL), 'IsIconic': ([W.HWND],W.BOOL),
            'GetWindowTextLengthW': ([W.HWND],C.c_int),
            'GetWindowTextW': ([W.HWND,W.LPWSTR,C.c_int],C.c_int),
            'GetWindowRect': ([W.HWND,C.POINTER(W.RECT)],W.BOOL),
            'GetWindowThreadProcessId': ([W.HWND,C.POINTER(W.DWORD)],W.DWORD),
            'GetWindowLongPtrW': ([W.HWND,C.c_int],C.c_ssize_t),
            'SetWindowLongPtrW': ([W.HWND,C.c_int,C.c_ssize_t],C.c_ssize_t),
            'SetWindowPos': ([W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT],W.BOOL),
            'SetForegroundWindow': ([W.HWND],W.BOOL),
            'SystemParametersInfoW': ([W.UINT,W.UINT,C.c_void_p,W.UINT],W.BOOL),
            'GetSystemMetrics': ([C.c_int],C.c_int),
            'GetCursorPos': ([C.POINTER(W.POINT)],W.BOOL),
        }
        for name,(args,result) in signatures.items():
            fn = getattr(self.user,name)
            fn.argtypes,fn.restype = args,result
        for name,args,result in (
            ('OpenProcess',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
            ('QueryFullProcessImageNameW',[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)],W.BOOL),
            ('CloseHandle',[W.HANDLE],W.BOOL),
        ):
            fn=getattr(self.kernel,name)
            fn.argtypes,fn.restype=args,result

    def connected(self):
        # Query cached Windows flags without initiating any network request.
        if not hasattr(self, '_internet'):
            self._internet = C.WinDLL('wininet', use_last_error=True)
            self._internet.InternetGetConnectedState.argtypes = [C.POINTER(W.DWORD), W.DWORD]
            self._internet.InternetGetConnectedState.restype = W.BOOL
        flags = W.DWORD()
        return bool(self._internet.InternetGetConnectedState(C.byref(flags), 0))

    def foreground(self, handle):
        return self.user.GetForegroundWindow()==handle

    def windows(self):
        now=time.monotonic()
        cached=getattr(self,'_windows',None)
        if cached is not None and now<self._scan_at and all(self.user.IsWindow(t.handle) for t in cached):
            for t in cached:
                rect=W.RECT()
                t.visible=bool(self.user.IsWindowVisible(t.handle))
                t.minimized=bool(self.user.IsIconic(t.handle))
                t.exstyle=self.user.GetWindowLongPtrW(t.handle,-20)
                t.owner=self.user.GetWindow(t.handle,4)
                if self.user.GetWindowRect(t.handle,C.byref(rect)):
                    t.rect=(rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top)
            return cached
        result=[]
        @self.enum_proc
        def visit(hwnd, _):
            if not self.user.IsWindowVisible(hwnd):
                return True
            length=self.user.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            title=C.create_unicode_buffer(length+1)
            self.user.GetWindowTextW(hwnd,title,length+1)
            pid=W.DWORD()
            self.user.GetWindowThreadProcessId(hwnd,C.byref(pid))
            process=self.kernel.OpenProcess(0x1000,False,pid.value)
            if not process:
                return True
            try:
                path=C.create_unicode_buffer(32768)
                size=W.DWORD(len(path))
                if self.kernel.QueryFullProcessImageNameW(process,0,path,C.byref(size)):
                    name=path.value.rsplit('\\',1)[-1]
                    if name.lower() in ('claude.exe','chatgpt.exe'):
                        rect=W.RECT()
                        if self.user.GetWindowRect(hwnd,C.byref(rect)):
                            result.append(Target(hwnd,name,title.value,(rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top),True,bool(self.user.IsIconic(hwnd)),self.user.GetWindowLongPtrW(hwnd,-20),self.user.GetWindow(hwnd,4)))
            finally:
                self.kernel.CloseHandle(process)
            return True
        self.user.EnumWindows(visit,0)
        self._windows=result
        self._scan_at=now+2
        if hasattr(self,'_notify'):
            self._bind_events()
        return result

    def attach(self, pet, owner):
        if self.user.GetWindowLongPtrW(pet,-20) & 0x00000008:  # WS_EX_TOPMOST
            self.user.SetWindowPos(pet,-2,0,0,0,0,0x0001|0x0002|0x0010)
        self.user.SetWindowLongPtrW(pet,-8,owner)  # GWLP_HWNDPARENT: owner for a popup
        # Do not raise above the foreground app: retain the owned-window Z order.
        self.user.SetWindowPos(pet,None,0,0,0,0,0x0001|0x0002|0x0004|0x0010|0x0200)

    def screen_rect(self):
        return tuple(self.user.GetSystemMetrics(i) for i in (76,77,78,79))

    def attach_aura(self, aura, pet, owner):
        # Same target owner, immediately behind the pet, without activation.
        # WindowTransparentForInput also maps to WS_EX_TRANSPARENT on Windows.
        style = self.user.GetWindowLongPtrW(aura,-20)
        self.user.SetWindowLongPtrW(aura,-20,style | 0x00000020 | 0x08000000)
        self.user.SetWindowLongPtrW(aura,-8,owner)
        self.user.SetWindowPos(aura,pet,0,0,0,0,0x0001|0x0002|0x0010|0x0200)

    def topmost(self, pet):
        self.user.SetWindowLongPtrW(pet,-8,0)
        self.user.SetWindowPos(pet,-1,0,0,0,0,0x0001|0x0002|0x0010|0x0200)

    def animations(self):
        enabled=W.BOOL(True)
        self.user.SystemParametersInfoW(0x1042,0,C.byref(enabled),0)  # SPI_GETCLIENTAREAANIMATION
        return bool(enabled.value)

    def cursor(self):
        point=W.POINT()
        self.user.GetCursorPos(C.byref(point))
        return point.x,point.y

    def activate(self, handle):
        self.user.SetForegroundWindow(handle)

    def watch(self, callback):
        """Out-of-context callbacks run on the installing Qt message-loop thread."""
        self._notify=callback
        self._hooks=[]
        self._hook_pid=None
        callback_type=C.WINFUNCTYPE(None,W.HANDLE,W.DWORD,W.HWND,C.c_long,C.c_long,W.DWORD,W.DWORD)
        @callback_type
        def changed(hook,event,hwnd,object_id,child_id,thread_id,event_time):
            targets=getattr(self,'_windows',[])
            if event==0x0003 or (object_id==0 and child_id==0 and any(t.handle==hwnd for t in targets)):
                if event==0x8001:
                    self._scan_at=0
                self._notify()
        self._event_callback=changed  # Keep the ctypes callback alive until unhooked.
        return self._bind_events()

    def _bind_events(self):
        targets=getattr(self,'_windows',[])
        pids=set()
        for target in targets:
            pid=W.DWORD()
            self.user.GetWindowThreadProcessId(target.handle,C.byref(pid))
            if pid.value:
                pids.add(pid.value)
        signature=tuple(sorted(pids))
        if self._hook_pid==signature:
            return self.events_available
        self.unwatch()
        self._hook_pid=signature
        events=[(0x0003,0)]
        for process in signature:
            events.extend((event,process) for event in (0x800B,0x8001,0x0016,0x0017,0x8002,0x8003))
        complete=True
        for event,process in events:
            hook=self.user.SetWinEventHook(event,event,None,self._event_callback,process,0,0)
            if hook:
                self._hooks.append(hook)
            else:
                complete=False
        self.events_available=complete
        return complete

    def unwatch(self):
        for hook in getattr(self,'_hooks',[]):
            self.user.UnhookWinEvent(hook)
        self._hooks=[]
        self._hook_pid=None
