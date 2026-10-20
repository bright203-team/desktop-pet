"""Local artwork and shared accessible settings styling."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath
from PySide6.QtWidgets import QDialog
from .model import ROOT

STYLE = '''
QWidget { font-family: 'Yu Gothic UI'; color: #493653; font-size: 13px; }
QDialog { background: #fff8f4; }
QWidget#details { background: #fffefa; border-radius: 12px; }
QListWidget::item:selected { background: #ffe0ed; color: #493653; border-radius: 9px; }
QListWidget, QScrollArea, QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {
 background: #fffefa; border: 1px solid #d9c8ea; border-radius: 9px; padding: 5px; }
QPushButton { background: #c9eddf; border: 1px solid #d9c8ea; border-radius: 12px; padding: 9px; }
QPushButton[primary="true"] { background: #f6b4cf; }
QPushButton:focus, QCheckBox:focus { border: 2px solid #77518e; }
QCheckBox { spacing: 7px; padding: 4px; }
QCheckBox::indicator { width: 30px; height: 17px; border-radius: 8px; border: 1px solid #aaa; background: #ccc; }
QCheckBox::indicator:checked { background: #ed91b9; border-color: #bb628c; }
QLabel#banner { background: #ffe0ed; border-radius: 10px; padding: 8px; }
'''

def style(widget):
    widget.setStyleSheet(STYLE)

def application_icon(root=ROOT, fallback=None):
    """Decode first so a missing or corrupt PNG never hides the old icon."""
    image = QPixmap(str(root/'assets/ui/icon.png'))
    return QIcon(image) if not image.isNull() else (fallback if fallback is not None else QIcon())


class ThemedDialog(QDialog):
    def __init__(self, parent=None, root=None):
        super().__init__(parent)
        root = root if root is not None else getattr(parent, 'root', ROOT)
        self.root = root
        self.setWindowIcon(application_icon(root, self.windowIcon()))
        style(self)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setOpacity(.07)
        pixmap = QPixmap(str(ROOT/'assets/ui/bg-pattern.png'))
        if not pixmap.isNull():
            painter.drawTiledPixmap(self.rect(), pixmap)
        painter.end()


def portrait(config, root=ROOT, size=48, circular=True):
    from .sprites import Sprites
    avatar = {'default':'flan', 'chiffon':'chiffon'}.get(config.id) if circular else None
    image = QPixmap(str(ROOT/f'assets/ui/avatar-{avatar}.png')) if avatar else QPixmap()
    folder = root/config.pet_folder
    if image.isNull():
        image = QPixmap(str(folder/'main.png'))
    if image.isNull():
        sprites = Sprites(folder, (192,208))
        frames = sprites.for_scene('idle_blink') if sprites.scene_format else sprites.rows['idle']
        image = QPixmap.fromImage(frames[0])
    image = image.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatioByExpanding if circular else Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(size,size); result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if circular:
        path = QPainterPath(); path.addEllipse(0,0,size,size); painter.setClipPath(path)
    painter.drawPixmap((size-image.width())//2,(size-image.height())//2,image)
    painter.end()
    return result
