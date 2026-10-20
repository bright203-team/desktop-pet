"""Startup shortcut boundary; folder and process runner are replaceable in tests."""
from pathlib import Path
import subprocess
from .model import ROOT
from .win32 import startup_folder


class StartupShortcut:
    def __init__(self, root=ROOT, folder=None, runner=None):
        self.root = Path(root)
        self.folder = Path(folder) if folder is not None else None
        self.runner = runner if runner is not None else subprocess.run

    def shortcut(self):
        folder = self.folder if self.folder is not None else startup_folder()
        return Path(folder)/'ClaudeDesktopPet.lnk'

    def enabled(self):
        # stat, rather than exists, preserves access errors for the settings UI.
        try:
            self.shortcut().stat()
            return True
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled):
        shortcut = self.shortcut()
        script = 'register-startup.ps1' if enabled else 'unregister-startup.ps1'
        result = self.runner([
            'powershell.exe', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
            '-ExecutionPolicy', 'Bypass', '-File', str(self.root/'scripts'/script),
            '-StartupFolder', str(shortcut.parent),
        ], capture_output=True, text=True, errors='replace', timeout=15,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            reason = (result.stderr or result.stdout).strip()
            raise OSError(reason or f'ショートカットの変更に失敗しました（終了コード {result.returncode}）')
        if self.enabled() != enabled:
            raise OSError('ショートカットの変更を確認できませんでした')
