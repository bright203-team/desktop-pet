"""Input-transparent aura, with no timer or change to the pet's geometry."""
import math
from PySide6.QtCore import Qt
from PySide6.QtGui import QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

FRAME_SECONDS = .1  # Independent of scene speed; at most ten aura frames/s.
AURA_SCALE = 1.3
AURA_OPACITY = .55


def aura_size(sprite_size):
    return tuple(max(1, round(side * AURA_SCALE)) for side in sprite_size)


def load_frames(root, sprite_size):
    result = []
    for number in range(1, 9):
        reader = QImageReader(str(root / 'assets/ui/aura' / f'aura-{number:02}.png'))
        size = reader.size()
        if (size.width(), size.height()) != (384, 416):
            return []
        image = reader.read()
        if image.isNull() or not image.hasAlphaChannel():
            return []
        result.append(QPixmap.fromImage(image.scaled(
            *aura_size(sprite_size),
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)))
    return result


class AuraWindow(QWidget):
    def __init__(self, pet):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                         | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.pet = pet
        self.frames = []
        self.started = None
        self.frame_index = 0
        self.next_frame = math.inf
        self.stacking = None

    def reload(self):
        self.hide()
        self.frames = load_frames(self.pet.root, self.pet.sprite_size)
        self.started = None
        self.next_frame = math.inf
        self.stacking = None
        self.setWindowOpacity(self.pet.config.opacity)
        self.resize(*aura_size(self.pet.sprite_size))

    def follow_pet(self):
        pet = self.pet
        self.move(pet.x()+(pet.sprite_size[0]-self.width())//2,
                  pet.y()+pet.bubble_height+(pet.sprite_size[1]-self.height())//2)

    def sync(self, now, visible):
        pet = self.pet
        if not (visible and pet.controller.aura_enabled and self.frames):
            self.hide()
            self.started = None
            self.next_frame = math.inf
            return
        if self.started is None:
            self.started = now
            self.frame_index = -1
        step = max(0, math.floor((now-self.started)/FRAME_SECONDS + 1e-9)) if pet.effects else 0
        index = step % len(self.frames)
        self.next_frame = self.started+(step+1)*FRAME_SECONDS if pet.effects else math.inf
        self.follow_pet()
        if index != self.frame_index:
            self.frame_index = index
            self.update()
        shown = self.isVisible()
        if not shown:
            self.show()
        target = pet.controller.target.handle
        stacking = (target, pet.config.movement)
        if not shown or self.stacking != stacking:
            pet.backend.attach_aura(int(self.winId()), int(pet.winId()),
                                    target if pet.config.movement != 'none' else 0)
            self.stacking = stacking

    def paintEvent(self, event):
        if self.frames and self.frame_index >= 0:
            painter = QPainter(self)
            painter.setOpacity(AURA_OPACITY)
            painter.drawPixmap(0, 0, self.frames[self.frame_index])
