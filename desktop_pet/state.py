"""Bounded local state-file polling and deterministic hook lifecycle."""
import json
import os
import time
from pathlib import Path
from datetime import datetime
from .model import durations


def state_path(source='claude-code'):
    if source == 'codex':
        return Path(os.environ.get('CODEX_PET_STATE_PATH') or
                    Path(os.environ.get('USERPROFILE') or Path.home())/'.claude-desktop-pet'/'codex-state.json')
    return Path(os.environ.get('CLAUDE_PET_STATE_PATH') or
                Path(os.environ.get('USERPROFILE') or Path.home())/'.claude-desktop-pet'/'state.json')


class StateController:
    """State lifecycle without files or external applications (also used by previews)."""
    def __init__(self, controller, clock=time.monotonic):
        self.controller = controller
        self.clock = clock
        self.phase = None
        self.changed = 0
        self.phase_end = 0

    def receive(self, state, expression='normal', message='', age=0, model=''):
        now = self.clock()
        self.controller.model = model if isinstance(model, str) and len(model) <= 256 else ''
        self.changed = now-age
        self.phase = state
        if state != 'sleeping' and age >= self.controller.config.idle_seconds:
            self.phase = None
            self.controller.set_state('idle', 'normal')
            return
        self.controller.set_state(state, expression, '寝ています' if state == 'sleeping' else '完了' if state == 'review' else '入力待ち' if state == 'waiting' else message[:80])
        if state == 'review':
            self.phase_end = self.changed+self.controller.config.review_seconds
        elif state == 'failed':
            self.phase_end = now+sum(durations('failed', 1, self.controller.config.speed))/1000

    def advance(self):
        now = self.clock()
        if self.phase is None or self.phase == 'sleeping':
            return
        config = self.controller.config
        if self.phase == 'review' and now >= self.phase_end:
            self.phase = 'waiting'
            self.changed = self.phase_end
            self.controller.set_state('waiting', self.controller.expression, '入力待ち')
        if self.phase != 'review' and now-self.changed >= config.idle_seconds:
            self.phase = None
            self.controller.set_state('idle', 'normal')
        elif self.phase == 'failed' and now >= self.phase_end:
            self.phase = 'running'
            self.controller.set_state('running', self.controller.expression, 'エラー')


class StateWatcher(StateController):
    def __init__(self, controller, path=None, clock=time.monotonic, wall=time.time, read_interval=0):
        super().__init__(controller, clock)
        self.path = Path(path) if path is not None else state_path()
        self.wall = wall
        self.signature = None
        self.foreground = False
        self.next_read = 0
        self.read_interval = read_interval

    def poll(self, foreground=False):
        now=self.clock()
        self.foreground=foreground
        try:
            if now < self.next_read:
                raise OSError("Polling interval")
            self.next_read=now+self.read_interval
            stat=self.path.stat()
            signature=(stat.st_mtime_ns,stat.st_size,stat.st_ino)
            if signature!=self.signature:
                self.signature=signature
                if stat.st_size>65536:
                    raise ValueError('State too large')
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(data,dict) or data.get('state') not in ('running','waiting','failed','review','sleeping'):
                    raise ValueError('Invalid state')
                if not isinstance(data.get('updated_at'),str):
                    raise ValueError('Invalid timestamp')
                stamp=datetime.fromisoformat(data['updated_at'].replace('Z','+00:00'))
                if stamp.tzinfo is None:
                    raise ValueError('Timestamp requires timezone')
                age=max(0,self.wall()-stamp.timestamp())
                expression=data.get('expression','normal')
                message=data.get('message','')
                if not isinstance(message,str) or not isinstance(expression,str):
                    raise ValueError('Invalid message')
                state=data['state']
                self.receive(state, expression, message, age, data.get('model', ''))
        except (OSError,ValueError,TypeError,KeyError,OverflowError):
            pass
        self.advance()


class NoStateWatcher:
    phase = None
    def poll(self, foreground=False):
        pass
