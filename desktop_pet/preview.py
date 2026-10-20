"""Local animation preview. Its clock, controllers and images never read hook state."""
from dataclasses import replace
import json
import math
from pathlib import Path
import time
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QWidget, QScrollArea, QGroupBox, QLabel, QPushButton, QDoubleSpinBox)
from .model import Controller
from .scene_runtime import SceneController
from .scenes import SCENES, IMPORT_SCENES, LEGACY
from .sprites import Sprites
from .state import StateController


class PreviewClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += max(0, seconds)


class PreviewModel:
    def __init__(self, config, root, clock=None):
        self.config = replace(config, scene_speeds=dict(config.scene_speeds))
        self.folder = Path(root)/Path(config.pet_folder).expanduser()
        self.clock = clock or PreviewClock()
        self.sprites = Sprites(self.folder, (144, 156))
        self.playing = True
        self.last = self.clock()
        self.elapsed = {scene: 0.0 for scene in SCENES}
        self.times = {scene: self.sprites.scene_durations(scene, config.scene_speed(scene)) for scene in SCENES}
        self.changed = set()
        self.demo_clock = PreviewClock()
        self.demo_active = False
        self.demo_scene = 'idle_blink'
        self.demo_elapsed = 0.0
        self.demo_next = None
        self._demo_controllers()

    def _demo_controllers(self):
        # Fixed ten seconds belongs to the demo; user settings remain untouched.
        self.controller = Controller(None, replace(self.config, review_seconds=10))
        self.states = StateController(self.controller, self.demo_clock)
        self.scenes = SceneController(self.controller.config, self.demo_clock)
        self.controller.scene_runtime = self.scenes

    def fallback(self, scene):
        if self.sprites.scene_format:
            if scene in self.sprites.scenes:
                return ''
            return '代わりの場面：まばたき' if 'idle_blink' in self.sprites.scenes else '画像なし：仮の図形'
        row = LEGACY[scene]
        return f'今の形式：{row} の段' if row in self.sprites.available_rows else f'画像なし：仮の図形（{row} の段）'

    def frame(self, scene):
        times = self.times[scene]
        elapsed = self.elapsed[scene]
        if scene == 'idle_sleep':
            elapsed = min(elapsed, sum(times)-.001)
        else:
            elapsed %= sum(times)
        for index, value in enumerate(times):
            if elapsed + 1e-6 < value:
                return index
            elapsed -= value
        return len(times)-1

    def tick(self):
        now = self.clock()
        delta = max(0, now-self.last)
        self.last = now
        if not self.playing:
            return
        for scene in SCENES:
            self.elapsed[scene] += delta*1000
        if self.demo_active:
            previous = self.demo_clock()
            self.demo_clock.advance(delta)
            if self.demo_next and self.demo_clock() >= 3:
                self.states.receive(self.demo_next)
                self.demo_next = None
            self.states.advance()
            self.demo_elapsed += (self.demo_clock()-previous)*1000
            if self.demo_scene == 'click' and self.demo_elapsed >= sum(self.times['click']):
                self.scenes.finish('click')
            scene = self.scenes.update(self.controller)
            if scene != self.demo_scene:
                self.demo_elapsed = 0
                self.demo_scene = scene

    def pause(self):
        self.tick()
        self.playing = not self.playing

    def restart(self):
        for scene in SCENES:
            self.elapsed[scene] = 0
        self.last = self.clock()
        self.playing = True
        if self.demo_active:
            self.start_demo(self.demo_kind)

    def step(self, scene):
        self.tick()
        index = (self.frame(scene)+1) % len(self.times[scene])
        self.elapsed[scene] = sum(self.times[scene][:index])
        self.playing = False

    def set_frame_ms(self, scene, milliseconds):
        if not math.isfinite(milliseconds) or milliseconds <= 0:
            raise ValueError('Invalid duration')
        factor = milliseconds/(sum(self.times[scene])/len(self.times[scene]))
        # Preserve the relative long pauses in sheets such as blinking.
        self.times[scene] = [max(1, value*factor) for value in self.times[scene]]
        self.elapsed[scene] = 0
        self.changed.add(scene)

    def start_demo(self, kind):
        self.demo_kind = kind
        self.demo_clock = PreviewClock()
        self._demo_controllers()
        self.demo_next = None
        if kind in ('done_wait', 'done_work'):
            self.states.receive('review')
            if kind == 'done_work':
                self.demo_next = 'running'
        else:
            self.states.receive('running')
            if kind == 'work_wait':
                self.demo_next = 'waiting'
            elif kind == 'click':
                self.scenes.click()
        self.demo_active = True
        self.demo_elapsed = 0
        self.demo_scene = self.scenes.update(self.controller)
        self.last = self.clock()
        self.playing = True

    def demo_frame(self):
        times = self.times[self.demo_scene]
        elapsed = self.demo_elapsed % sum(times)
        for index, value in enumerate(times):
            if elapsed + 1e-6 < value:
                return index
            elapsed -= value
        return len(times)-1

    def save(self, save_config):
        """Write only on explicit Save. Atomic replacement preserves unrelated metadata."""
        if not self.changed:
            return
        if self.sprites.scene_format:
            path = self.folder/'scenes.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError('場面の設定を読み込めません。')
            entries = data.get('scenes', data)
            if not isinstance(entries, dict):
                raise ValueError('場面の設定を読み込めません。')
            for scene in self.changed:
                source = scene if scene in self.sprites.scenes else 'idle_blink'
                if source not in self.sprites.scenes:
                    raise ValueError('画像のある場面を読み込んでから保存してください。')
                entry = dict(entries[source])
                # Runtime divides by config speed; store the underlying durations.
                values = [value*self.config.scene_speed(scene) for value in self.times[scene]]
                if any(not math.isfinite(value) or not 0 < value < 86400000 for value in values):
                    raise ValueError('コマの時間が保存できる範囲を超えています。')
                entry['durations'] = values
                entries[scene] = entry
            temporary = path.with_name(f'.scenes-{uuid4().hex}.tmp')
            try:
                temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            speeds = dict(self.config.scene_speeds)
            for scene in self.changed:
                original = self.sprites.scene_durations(scene, self.config.speed)
                speed = sum(original)/sum(self.times[scene])
                if not .05 <= speed <= 10:
                    raise ValueError('今の形式の速さは元の0.05〜10倍の範囲で保存してください。')
                speeds[scene] = speed
            config = replace(self.config, scene_speeds=speeds)
            if save_config(config) is False:
                raise OSError('設定を保存できません。')
            self.config = config
        self.changed.clear()


from .theme import ThemedDialog

class AnimationPreview(ThemedDialog):
    def __init__(self, config, root, save_config, on_saved=None, parent=None, clock=time.monotonic):
        super().__init__(parent)
        self.setWindowTitle(f'アニメのプレビュー：{config.display_name}')
        self.resize(920, 760)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.model = PreviewModel(config, root)
        self.save_config, self.on_saved = save_config, on_saved
        self.wall_clock = clock
        self.wall_last = clock()
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.advance)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.play = QPushButton('一時停止')
        self.play.clicked.connect(self.toggle)
        controls.addWidget(self.play)
        restart = QPushButton('全体を最初から')
        restart.clicked.connect(self.restart)
        controls.addWidget(restart)
        save = QPushButton('保存')
        save.clicked.connect(self.save)
        controls.addWidget(save)
        layout.addLayout(controls)
        self.error = QLabel('時間の変更は「保存」を押したときだけ反映します。')
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        demo = QGroupBox('切り替えのデモ（実際のAIには接続しません）')
        demo_layout = QVBoxLayout(demo)
        row = QHBoxLayout()
        for text, kind in (('完了10秒 → 返事・許可待ち', 'done_wait'), ('完了中に次の作業', 'done_work'),
                           ('作業中に承認待ち', 'work_wait'), ('クリック → 元の場面', 'click')):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, kind=kind: self.start_demo(kind))
            row.addWidget(button)
        demo_layout.addLayout(row)
        self.demo_image = QLabel()
        self.demo_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.demo_status = QLabel('ボタンで切り替えを試せます。次の状態は3秒後に届きます。')
        demo_layout.addWidget(self.demo_image)
        demo_layout.addWidget(self.demo_status)
        layout.addWidget(demo)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        self.cards = {}
        for number, scene in enumerate(IMPORT_SCENES):
            card = QGroupBox(f'{number+1:02} {SCENES[scene]}')
            box = QVBoxLayout(card)
            image, label = QLabel(), QLabel()
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(image)
            box.addWidget(label)
            fallback = QLabel(self.model.fallback(scene))
            fallback.setWordWrap(True)
            box.addWidget(fallback)
            step = QPushButton('コマ送り')
            step.clicked.connect(lambda checked=False, scene=scene: self.step(scene))
            box.addWidget(step)
            duration = QDoubleSpinBox()
            duration.setRange(1, 1000000)
            duration.setSuffix(' ms / コマ（平均）')
            duration.setValue(sum(self.model.times[scene])/len(self.model.times[scene]))
            duration.valueChanged.connect(lambda value, scene=scene: self.model.set_frame_ms(scene, value))
            box.addWidget(duration)
            self.cards[scene] = (image, label)
            grid.addWidget(card, number//3, number%3)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        self.render()

    def showEvent(self, event):
        self.wall_last = self.wall_clock()
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

    def advance(self):
        now = self.wall_clock()
        self.model.clock.advance(now-self.wall_last)
        self.wall_last = now
        self.model.tick()
        self.render()

    def render(self):
        for scene, (image, label) in self.cards.items():
            index = self.model.frame(scene)
            image.setPixmap(QPixmap.fromImage(self.model.sprites.for_scene(scene)[index]))
            label.setText(f'コマ {index+1} / {len(self.model.times[scene])}')
        if self.model.demo_active:
            scene = self.model.demo_scene
            self.demo_image.setPixmap(QPixmap.fromImage(self.model.sprites.for_scene(scene)[self.model.demo_frame()]))
            remaining = max(0, self.model.states.phase_end-self.model.demo_clock()) if self.model.states.phase == 'review' else 0
            suffix = f'（残り {math.ceil(remaining)} 秒）' if remaining else ''
            self.demo_status.setText(f'今の場面：{SCENES[scene]} {suffix}')
        self.play.setText('一時停止' if self.model.playing else '全体を再生')

    def toggle(self):
        self.model.pause()
        self.render()

    def restart(self):
        self.model.restart()
        self.render()

    def step(self, scene):
        self.model.step(scene)
        self.render()

    def start_demo(self, kind):
        self.model.start_demo(kind)
        self.render()

    def save(self):
        try:
            self.model.save(self.save_config)
            if self.on_saved:
                self.on_saved()
            self.error.setText('保存しました。動いているキャラにも反映されます。')
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.error.setText(f'保存できません：{error}')
