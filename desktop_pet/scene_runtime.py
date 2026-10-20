"""Event-driven scene selection; independent of Qt, images and operating system."""
import random
import time

DEFAULT_PRIORITY = ('drag', 'click', 'offline', 'waiting', 'working', 'done', 'hover', 'idle')
LEGACY_SCENES = {'idle': 'idle_blink', 'running': 'working', 'waiting': 'waiting',
                 'review': 'done', 'failed': 'working', 'jumping': 'hover',
                 'waving': 'click', 'running-right': 'drag_right', 'running-left': 'drag_left',
                 'sleeping': 'offline'}


class SceneController:
    def __init__(self, config, clock=time.monotonic, rng=None):
        self.config, self.clock = config, clock
        self.rng = rng or random.Random()
        self.scene = 'idle_blink'
        self.held = False
        self._last_activity = clock()
        self._next_idle = clock() + self._interval()
        self._last_idle = None
        self._idle = 'idle_blink'
        self._hovering = False
        self._hover = False
        self._click = False
        self._drag = None
        self._offline_since = None
        self._revision = None
        self._selection_key = None
        self.next_change = 0

    def _get(self, name, default):
        return getattr(self.config, name, default)

    def _interval(self):
        low = self._get('idle_min_seconds', 20)
        high = self._get('idle_max_seconds', 40)
        return self.rng.uniform(min(low, high), max(low, high))

    def activity(self):
        self._selection_key = None
        self._last_activity = self.clock()
        self._idle = 'idle_blink'
        self.held = False
        self._next_idle = self.clock() + self._interval()

    def hover(self):
        self.activity()
        self._hover = True

    def click(self):
        self.activity()
        if self._click and not self._get('click_restart', False):
            return False
        self._click = True
        return True

    def drag(self, direction):
        self.activity()
        self._drag = 'drag_left' if direction == 'left' or (isinstance(direction, (int, float)) and direction < 0) else 'drag_right'
        self._click = False
        self._hover = False

    def release(self):
        self._drag = None
        self.activity()

    def finish(self, scene):
        """Called once when the renderer reaches the end of a scene cycle."""
        self._selection_key = None
        if scene == 'click':
            self._click = False
        elif scene == 'hover':
            self._hover = bool(self._hovering and self._get('hover_repeat', False))
        elif scene == 'idle_sleep' and self._idle == scene:
            self.held = True
        elif scene == self._idle and scene != 'idle_blink':
            self._idle = 'idle_blink'
            self._next_idle = self.clock() + self._interval()

    def update(self, controller, connected=True, hovering=False):
        now = self.clock()
        key = (getattr(controller, 'revision', 0), getattr(controller, 'base_state', controller.state),
               connected, hovering, vars(self.config), self._click, self._hover, self._drag)
        if key == self._selection_key and now < self.next_change:
            return self.scene
        revision = getattr(controller, 'revision', 0)
        if revision != self._revision:
            if self._revision is not None:
                self.activity()
            self._revision = revision
        if hovering and not self._hovering:
            self.hover()
        self._hovering = hovering
        if connected:
            self._offline_since = None
        elif self._offline_since is None:
            self._offline_since = now
        offline = (self._get('offline_enabled', True) and self._offline_since is not None
                   and now - self._offline_since >= self._get('offline_seconds', 30))
        base = LEGACY_SCENES.get(getattr(controller, 'base_state', controller.state), 'idle_blink')
        if base == 'idle_blink' and not (self._click or self._hover or self._drag or offline):
            if now - self._last_activity >= self._get('sleep_seconds', 180):
                self._idle = 'idle_sleep'
            elif self._idle == 'idle_blink' and now >= self._next_idle:
                choices = ['idle_smug', 'idle_peek', 'idle_play']
                if self._get('idle_order', 'random') == 'sequential':
                    index = (choices.index(self._last_idle) + 1) % len(choices) if self._last_idle in choices else 0
                    self._idle = choices[index]
                else:
                    self._idle = self.rng.choice([s for s in choices if s != self._last_idle])
                self._last_idle = self._idle
        candidates = {'idle': self._idle}
        if self._drag:
            candidates['drag'] = self._drag
        if self._click:
            candidates['click'] = 'click'
        if self._hover:
            candidates['hover'] = 'hover'
        if offline:
            candidates['offline'] = 'offline'
        if base != 'idle_blink':
            category = 'drag' if base.startswith('drag_') else base
            candidates.setdefault(category, base)
        raw = self._get('scene_priority', ','.join(DEFAULT_PRIORITY))
        priority = raw.split(',') if isinstance(raw, str) else raw
        ordered = [s.strip() for s in priority if isinstance(s, str)]
        ordered += [s for s in DEFAULT_PRIORITY if s not in ordered]
        self.scene = next(candidates[key] for key in ordered if key in candidates)
        self.held = self.held and self.scene == 'idle_sleep'
        self._selection_key = (revision, getattr(controller, 'base_state', controller.state),
                               connected, hovering, vars(self.config).copy(), self._click, self._hover, self._drag)
        deadlines = []
        if base == 'idle_blink' and not (self._click or self._hover or self._drag or offline):
            if self._idle == 'idle_blink' and self._next_idle > now:
                deadlines.append(self._next_idle)
            sleep_at = self._last_activity + self._get('sleep_seconds', 180)
            if sleep_at > now:
                deadlines.append(sleep_at)
        if self._get('offline_enabled', True) and self._offline_since is not None and not offline:
            deadlines.append(self._offline_since + self._get('offline_seconds', 30))
        self.next_change = min(deadlines, default=float('inf'))
        return self.scene
