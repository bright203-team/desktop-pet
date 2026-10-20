"""Configuration, geometry and animation rules, independent of Win32."""
from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parent.parent
CAPTION_COLORS = {'pink': '#f3a3c4', 'lavender': '#c4b0ee', 'mint': '#a1dfc4',
                  'blue': '#9ed5f1', 'cream': '#f3dda0'}


def data_root(root=ROOT):
    """Installed copies keep user data outside the replaceable app directory."""
    root = Path(root)
    return root.parent if (root / '.installed-pet').is_file() else root


def config_path(root=ROOT):
    return data_root(root) / 'config.json'


@dataclass
class Config:
    id: str = 'default'
    display_name: str = 'フラン'
    movement: str = 'claude'
    source: str = 'claude-code'
    incoming_name: str = ''
    source_sha: str = ''
    enabled: bool = True
    scale: float = 1.0
    initial_x: float = 0.8
    initial_y: float = 0.7
    opacity: float = 1.0
    min_width: int = 400
    min_height: int = 300
    speed: float = 1.0
    scene_speeds: dict = field(default_factory=dict)
    bubble: bool = True
    strong_model_aura: bool = True
    pc_label: str = ''
    caption_color: str = 'pink'
    pet_folder: str = 'assets/pets/flan'
    gaze_radius: float = 240
    review_seconds: float = 10
    idle_seconds: float = 120
    idle_min_seconds: float = 20
    idle_max_seconds: float = 40
    sleep_seconds: float = 180
    idle_order: str = 'random'
    scene_priority: str = 'drag,click,offline,waiting,working,done,hover,idle'
    offline_enabled: bool = True
    offline_seconds: float = 30
    hover_repeat: bool = False
    click_restart: bool = False
    scene_gaze: bool = False

    def scene_speed(self, scene):
        return max(.001, self.speed*self.scene_speeds.get(scene, 1))

    @classmethod
    def load(cls, path):
        try:
            raw = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            raw = {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw, defaults=None):
        result = cls(**(defaults or {}))
        try:
            if not isinstance(raw, dict):
                return result
            for key, default in asdict(result).items():
                value = raw.get(key, default)
                if key == 'scene_speeds':
                    from .scenes import SCENES
                    if isinstance(value, dict):
                        result.scene_speeds = {name: number for name, number in value.items()
                            if name in SCENES and type(number) in (int, float)
                            and math.isfinite(number) and .05 <= number <= 10}
                    continue
                if isinstance(default, bool):
                    valid = isinstance(value, bool)
                elif isinstance(default, str):
                    valid = isinstance(value, str)
                else:
                    valid = isinstance(value, (float, int)) and not isinstance(value, bool) and (not isinstance(value, float) or math.isfinite(value))
                    if valid:
                        if key in ('initial_x', 'initial_y', 'opacity'):
                            valid = 0 <= value <= 1
                        elif key in ('scale', 'speed'):
                            valid = 0.05 <= value <= 10
                        else:
                            valid = 0 <= value <= 100000
                if key == 'idle_order':
                    valid = value in ('random', 'sequential')
                if key == 'scene_priority':
                    valid = isinstance(value, str) and len(value.split(',')) == 8 and set(value.split(',')) == {'drag','click','offline','waiting','working','done','hover','idle'}
                if key == 'movement':
                    valid = value in ('claude', 'chatgpt', 'none')
                if key == 'source':
                    valid = value in ('claude-code', 'codex', 'none')
                if key == 'caption_color':
                    valid = isinstance(value, str) and value in CAPTION_COLORS
                if valid:
                    setattr(result, key, value)
        except (OSError, ValueError, TypeError):
            pass
        return result

TIMES = {
    'idle': [280,110,110,140,140,320],
    'running-right': [120]*7+[220], 'running-left': [120]*7+[220],
    'waving': [140]*3+[280], 'jumping': [140]*4+[280],
    'failed': [140]*7+[240], 'waiting': [150]*5+[260],
    'running': [120]*5+[220], 'review': [150]*5+[280],
}
STATES = tuple(TIMES)

def durations(state, count, speed=1):
    source = TIMES.get(state, TIMES['idle'])
    if count <= 0:
        return []
    if count == len(source):
        values = source
    elif count == 1:
        values = [sum(source)]
    else:
        # Preserve total cycle and the official last/ordinary-frame ratio.
        ratio = source[-1] / (sum(source[:-1]) / (len(source)-1))
        ordinary = sum(source) / (count - 1 + ratio)
        values = [ordinary]*(count-1)+[ordinary*ratio]
    return [max(1, round(v / speed)) for v in values]

def gaze_index(dx, dy):
    return int((math.degrees(math.atan2(dx, -dy)) % 360 + 11.25) // 22.5) % 16

def clamp(value, low, high):
    return max(low, min(value, high))

def position(rect, size, ratio):
    x,y,w,h = rect
    return (round(x + max(0,w-size[0])*ratio[0]), round(y + max(0,h-size[1])*ratio[1]))

def ratios(rect, size, point):
    x,y,w,h = rect
    return (clamp((point[0]-x)/max(1,w-size[0]),0,1), clamp((point[1]-y)/max(1,h-size[1]),0,1))

def load_position(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        if len(value) == 2 and all(type(v) in (int,float) and 0<=v<=1 for v in value):
            return tuple(value)
    except (OSError, ValueError, TypeError):
        pass
    return default

def save_position(path, ratio):
    try:
        path = Path(path)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(ratio), encoding='utf-8')
        temp.replace(path)
    except OSError:
        pass

@dataclass
class Target:
    handle: int
    process: str
    title: str
    rect: tuple
    visible: bool = True
    minimized: bool = False
    exstyle: int = 0
    owner: int = 0

def choose_target(windows, process="claude"):
    return max((w for w in windows if w.process.lower() in (process, process+'.exe') and w.visible and w.title.strip() and not w.exstyle & (0x80 | 0x20) and not w.owner),
               key=lambda w: w.rect[2]*w.rect[3], default=None)

class Controller:
    def __init__(self, backend, config):
        self.backend, self.config = backend, config
        self.enabled = config.enabled
        self.target = None
        self.state = 'idle'
        self.base_state = 'idle'
        self.expression = 'normal'
        self.message = ''
        self.model = ''
        self.dragging = False
        self.revision = 0

    def poll(self):
        self.target = (Target(0, '', 'Desktop', self.backend.screen_rect())
                       if self.config.movement == 'none' else
                       choose_target(self.backend.windows(), self.config.movement))
        t = self.target
        return bool(self.enabled and t and not t.minimized and t.rect[2]>=self.config.min_width and t.rect[3]>=self.config.min_height)

    def set_state(self, state, expression='normal', message=''):
        self.revision += 1
        self.state = state if state in STATES or state == 'sleeping' else 'idle'
        if self.state not in ('jumping','waving','running-right','running-left'):
            self.base_state = self.state
        runtime=getattr(self,'scene_runtime',None)
        if runtime and self.state in ('jumping','waving'):
            runtime.hover() if self.state=='jumping' else runtime.click()
        self.expression = expression if expression in ('normal','smile','angry') else 'normal'
        self.message = str(message)

    @property
    def aura_enabled(self):
        marker = {'claude-code': 'fable', 'codex': 'astra'}.get(self.config.source)
        return bool(self.config.strong_model_aura and self.state == 'running'
                    and marker and marker in self.model.lower())

    def hover(self):
        if not self.dragging:
            if hasattr(self,'scene_runtime'): self.scene_runtime.hover()
            self.state = 'jumping'

    def drag(self, previous_x, current_x):
        if hasattr(self,'scene_runtime'): self.scene_runtime.drag(current_x-previous_x)
        self.dragging = True
        self.state = 'running-right' if current_x >= previous_x else 'running-left'

    def release(self, moved):
        if hasattr(self,'scene_runtime'):
            self.scene_runtime.release() if moved else self.scene_runtime.click()
        self.dragging = False
        self.state = 'idle' if moved else 'waving'


BUILTIN_PETS = (
    dict(id='default', display_name='フラン', movement='claude',
         source='claude-code', pet_folder='assets/pets/flan'),
    dict(id='chiffon', display_name='シフォン', movement='chatgpt',
         source='codex', pet_folder='assets/pets/chiffon'),
)
BUILTIN_IDS = frozenset(item['id'] for item in BUILTIN_PETS)


def normalize_configs(configs):
    """Restore fixed identities first and keep editable user preferences."""
    fixed, custom, used = {}, [], set(BUILTIN_IDS)
    for index, config in enumerate(configs):
        if config.id in BUILTIN_IDS:
            fixed.setdefault(config.id, config)
        else:
            config = Config.from_dict(asdict(config))
            if not config.id or config.id in used:
                config.id = f'pet-{index}'
                while config.id in used:
                    config.id += '-new'
            used.add(config.id)
            custom.append(config)
    result = []
    for defaults in BUILTIN_PETS:
        config = fixed.get(defaults['id'], Config(**defaults))
        values = asdict(config)
        from .character import characters_root
        folder = Path(config.pet_folder)
        valid = False
        try:
            if folder.resolve().is_relative_to(characters_root().resolve()):
                from .character_images import inspect_scenes
                inspect_scenes(folder, numbered=True, stored=True)
                from .sprites import Sprites
                sprites = Sprites(folder, (192,208))
                meta = json.loads((folder/'pet.json').read_text(encoding='utf-8'))
                valid = isinstance(meta, dict) and meta.get('sceneFormatVersion') == 1 and sprites.scene_format and len(sprites.scenes) == 13
        except (OSError, ValueError, TypeError):
            pass
        if not valid:
            values['pet_folder'] = defaults['pet_folder']
            values['source_sha'] = ''
        result.append(Config.from_dict(values, defaults))
    return result + custom


def load_configs(path):
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        if isinstance(raw, dict) and isinstance(raw.get('pets'), list):
            result = []
            for index, item in enumerate(raw['pets']):
                if not isinstance(item, dict):
                    continue
                if not isinstance(item.get('id'), str):
                    item = dict(item, id=f'pet-{index}')
                defaults = next((entry for entry in BUILTIN_PETS if entry['id'] == item['id']), {})
                config = Config.from_dict(item, defaults)
                result.append(config)
            return normalize_configs(result)
        defaults = next((entry for entry in BUILTIN_PETS
                         if isinstance(raw, dict) and entry['id'] == raw.get('id')), {})
        return normalize_configs([Config.from_dict(raw, defaults)])
    except (OSError, ValueError, TypeError):
        return normalize_configs([])


def save_configs(path, configs):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'pets': [asdict(c) for c in normalize_configs(configs)]}, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def position_path(root, pet_id):
    # Encode arbitrary IDs rather than accepting file-system paths from config.
    return data_root(root) / ('position.json' if pet_id == 'default' else 'position-' + pet_id.encode('utf-8').hex() + '.json')
