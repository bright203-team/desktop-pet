"""Load Codex pet sheets without assuming every column is populated."""
import json
from pathlib import Path
from PySide6.QtGui import QImage, QColor, QPainter
from .model import STATES
from .scenes import SCENES, LEGACY
from PySide6.QtCore import QSize, Qt

WIDTH, HEIGHT = 192, 208

def frames(image, row):
    result = []
    for col in range(8):
        frame = image.copy(col*WIDTH, row*HEIGHT, WIDTH, HEIGHT)
        if any(frame.pixelColor(x,y).alpha() for y in range(HEIGHT) for x in range(WIDTH)):
            result.append(frame)
    return result

class Sprites:
    def __init__(self, folder, size=None):
        self.scene_format = False
        self.scenes = {}
        self.durations = {}
        self.display_size = size
        self.rows = {}
        self.expressions = {}
        self.gaze = []
        self.version = 1
        try:
            folder = Path(folder)
            meta = json.loads((folder/'pet.json').read_text(encoding='utf-8'))
            version = meta['spriteVersionNumber']
            if version not in (1,2):
                raise ValueError('unknown sprite version')
            image = QImage(str(folder/meta['spritesheetPath']))
            if image.isNull() or image.width()!=1536 or image.height()!=(1872 if version==1 else 2288):
                raise ValueError('invalid sheet dimensions')
            self.version = version
            for row, state in enumerate(STATES):
                self.rows[state] = frames(image, row)
            if version == 2:
                # Gaze columns have fixed direction indices, even if transparent.
                self.gaze = [image.copy(c*WIDTH,r*HEIGHT,WIDTH,HEIGHT) for r in (9,10) for c in range(8)]
            for expression in ('smile','angry'):
                for suffix in ('png','webp'):
                    extra = QImage(str(folder/f'idle_{expression}.{suffix}'))
                    if not extra.isNull() and extra.size().width()==1536 and extra.height()==208:
                        self.expressions[expression] = frames(extra,0)
                        break
        except (OSError, ValueError, TypeError, KeyError):
            self.rows = {}
            self.gaze = []
        self.available_rows = {state for state, sequence in self.rows.items() if sequence}
        self._load_scenes(folder)
        fallback = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32)
        fallback.fill(QColor(0,0,0,0))
        painter = QPainter(fallback)
        painter.setBrush(QColor('#eeadbb'))
        painter.drawEllipse(32,40,128,152)
        painter.end()
        for state in STATES:
            if not self.rows.get(state):
                self.rows[state] = [fallback]

    def for_state(self, state, expression='normal'):
        if state == 'idle' and self.expressions.get(expression):
            return self.expressions[expression]
        return self.rows.get(state, self.rows['idle'])

    def _scaled(self, image):
        size = self.display_size
        if size is None:
            size = QSize(WIDTH, HEIGHT)
        if isinstance(size, (tuple, list)):
            size = QSize(*size)
        if isinstance(size, (int, float)):
            size = QSize(round(WIDTH*size), round(HEIGHT*size))
        scaled = image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        canvas = QImage(size, QImage.Format.Format_ARGB32)
        canvas.fill(0)
        painter = QPainter(canvas)
        painter.drawImage((size.width()-scaled.width())//2, (size.height()-scaled.height())//2, scaled)
        painter.end()
        return canvas

    def _load_scenes(self, folder):
        try:
            path = Path(folder) / 'scenes.json'
            self.scene_format = path.exists()
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict): return
            entries = data.get('scenes', data)
            if not isinstance(entries, dict): return
        except (OSError, ValueError, TypeError):
            return
        for scene in SCENES:
            try:
                entry = entries[scene]
                columns, rows, count = (entry[key] for key in ('columns','rows','frames'))
                if any(type(n) is not int or n <= 0 for n in (columns, rows, count)) or count > columns*rows or count > 4096: continue
                filename = Path(entry['file'])
                if filename.is_absolute() or '..' in filename.parts: continue
                image = QImage(str(Path(folder)/filename))
                if image.isNull() or image.width() < columns or image.height() < rows: continue
                durations = entry['durations']
                if not isinstance(durations, list) or len(durations) != count or any(type(n) not in (int,float) or not 0 < n < 86400000 for n in durations): continue
                result = []
                for index in range(count):
                    col, row = index % columns, index // columns
                    x, y = col*image.width()//columns, row*image.height()//rows
                    right, bottom = (col+1)*image.width()//columns, (row+1)*image.height()//rows
                    frame = self._scaled(image.copy(x,y,right-x,bottom-y))
                    if entry.get('mirror') is True:
                        # Reflect the cached display frame so scaling roundoff
                        # cannot introduce differences from the rightward frame.
                        frame = frame.mirrored(True, False)
                    result.append(frame)
                self.scenes[scene] = result
                self.durations[scene] = durations
            except (KeyError, TypeError, ValueError, OSError, AttributeError):
                continue

    def for_scene(self, scene, expression='normal'):
        if not self.scene_format:
            return self.for_state(LEGACY.get(scene, 'idle'), expression)
        return self.scenes.get(scene, self.scenes.get('idle_blink', self.rows['idle']))

    def scene_durations(self, scene, speed=1):
        speed = speed if isinstance(speed, (int,float)) and speed > 0 else 1
        if not self.scene_format:
            from .model import durations
            return durations(LEGACY.get(scene, 'idle'), len(self.for_scene(scene)), speed)
        values = self.durations.get(scene, self.durations.get('idle_blink', [1000]))
        return [max(1, value/speed) for value in values]
