"""Read-only integration diagnostics and an in-memory animation test."""
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import time
from .model import Controller
from .state import state_path


CODEX_GUIDE = (
    'Codex デスクトップアプリ：設定 → フック → ユーザー設定を開き、'
    'キャラ用5件（UserPromptSubmit・PreToolUse・PermissionRequest・PostToolUse・Stop）が'
    '「有効」かつ「信頼済み」か確認してください。\n'
    'Codex CLI： /hooks を開き、同じ5件を信頼してください。\n'
    '設定後は新しいチャット（セッション）で確かめてください。'
    'WSL は WSL 側の Codex で同じ手順を行います。'
    '通常の利用でターミナルを開いておく必要はありません。'
)
CLAUDE_GUIDE = 'Claude Code の新しいセッションで確かめてください。連動なしで導入した場合は、導入時に連動先を選んでください。'


def read_json(path, limit=1048576):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            return {}
        data = json.loads(raw.decode('utf-8-sig'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def registered(path, script):
    """Only our exact command, not arbitrary other hooks or a similar filename."""
    hooks = read_json(path).get('hooks', {})
    if not isinstance(hooks, dict):
        return False
    expected = str(script).replace('\\', '/').casefold()
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            handlers = group.get('hooks', []) if isinstance(group, dict) else []
            if not isinstance(handlers, list):
                continue
            for handler in handlers:
                if not isinstance(handler, dict) or handler.get('type') != 'command':
                    continue
                for key in ('command', 'commandWindows'):
                    command = handler.get(key, '')
                    if not isinstance(command, str):
                        continue
                    match = re.fullmatch(r'node "([^"\r\n]+)"(?: --state-path "[^"\r\n]*")?(?: --created-event)?(?: --created-hooks)?(?:; exit \$LASTEXITCODE)?', command)
                    if match and match[1].replace('\\', '/').casefold() == expected:
                        return True
    return False


@dataclass(frozen=True)
class IntegrationStatus:
    label: str
    registered: bool
    last_received: float | None = None
    note: str = ''

    @property
    def text(self):
        if not self.registered:
            return '登録なし'
        if self.last_received is None:
            return '登録済み・まだ通知なし'
        try:
            stamp = datetime.fromtimestamp(self.last_received).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
        except (ValueError, OSError, OverflowError):
            return '登録済み・まだ通知なし'
        return f'連動中（最後に通知を受け取った時刻：{stamp}）'


def received_mtime(path):
    data = read_json(path, 65536)
    if data.get('state') not in ('running', 'waiting', 'failed', 'review', 'sleeping'):
        return None
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def integration_statuses(root, home=None):
    home = Path(home) if home is not None else Path(os.environ.get('USERPROFILE') or Path.home())
    base = home/'.claude-desktop-pet'
    targets = read_json(base/'installation.json').get('targets', [])
    targets = [t for t in targets if isinstance(t, dict) and isinstance(t.get('path'), str)] if isinstance(targets, list) else []
    codex_home = Path(os.environ.get('CODEX_HOME') or home/'.codex')
    results = []
    for kind, label, fallback, script, source in (
        ('claude', 'Claude Code', home/'.claude/settings.json', 'state-hook.mjs', 'claude-code'),
        ('codex', 'Codex Windows', codex_home/'hooks.json', 'codex-hook.mjs', 'codex'),
        ('wsl', 'Codex WSL', None, 'codex-hook.mjs', 'codex'),
    ):
        paths = [t['path'] for t in targets if t.get('kind') == kind]
        if fallback is not None:
            paths.append(fallback)
        # WSL registration is recorded by the installer. Do not start a distro,
        # invoke a shell, or probe network/UNC paths from the settings window.
        linked = bool(paths) if kind == 'wsl' else any(registered(p, Path(root)/'scripts/pet'/script) for p in paths)
        note = ('Windows・WSL 共通の最終通知です。通知元は区別できません。' if source == 'codex' else '')
        if kind == 'wsl':
            note += ' 登録は導入時の記録です。WSL 側の現在の登録は確認手順で確かめてください。'
        results.append(IntegrationStatus(label, linked, received_mtime(state_path(source)) if linked else None, note))
    return results


class LinkTest:
    """Keep the watcher live on a shadow controller; never publish fake hooks."""
    FIELDS = ('state', 'base_state', 'expression', 'message', 'model')
    STEPS = (('running', '作業中'), ('waiting', '返事待ち'), ('review', '完了'))

    def __init__(self, controller, watcher, clock=time.monotonic, seconds=3):
        self.controller, self.watcher = controller, watcher
        self.clock, self.seconds = clock, seconds
        self.active = False
        self.index = -1

    def start(self):
        if self.active:
            return
        self.shadow = Controller(self.controller.backend, self.controller.config)
        for field in self.FIELDS:
            setattr(self.shadow, field, getattr(self.controller, field))
        self.watcher.controller = self.shadow
        self.started = self.clock()
        self.active = True
        self.advance()

    def advance(self):
        if not self.active:
            return
        index = int((self.clock() - self.started) / self.seconds)
        if index >= len(self.STEPS):
            self.cancel()
        elif index != self.index or self.controller.state != self.STEPS[index][0]:
            self.index = index
            state, message = self.STEPS[index]
            self.controller.model = ''
            self.controller.set_state(state, 'normal', message)

    def cancel(self):
        if not self.active:
            return
        self.active = False
        self.index = -1
        self.watcher.controller = self.controller
        for field in self.FIELDS:
            setattr(self.controller, field, getattr(self.shadow, field))
        self.controller.revision += 1

