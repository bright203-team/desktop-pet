"""Copy approved instructions and confirm incoming characters."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QComboBox)
from .character import CharacterFlow, incoming_root
from .character_images import inspect_scenes, import_scenes, source_sha
from .theme import ThemedDialog
from .scenes import IMPORT_SCENES, SCENES


class CharacterDialog(ThemedDialog):
    def __init__(self, parent=None, on_import=None):
        super().__init__(parent)
        self.on_import = on_import
        self.character_name = None
        self.flow = CharacterFlow()
        self.result_folder = None
        self.setWindowTitle('キャラを追加')
        self.resize(660, 540)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('キャラの名前'))
        self.name = QLineEdit()
        layout.addWidget(self.name)
        self.prompt_text = QPlainTextEdit()
        self.prompt_text.setReadOnly(True)
        self.prompt_text.hide()
        layout.addWidget(self.prompt_text)
        self.location = QLabel()
        self.location.setWordWrap(True)
        layout.addWidget(self.location)
        self.error = QLabel()
        layout.addWidget(self.error)
        self.previous = QPushButton('戻る')
        self.previous.clicked.connect(self.back)
        self.previous.setEnabled(False)
        self.next = QPushButton('次へ')
        self.next.clicked.connect(self.advance)
        self.copy = QPushButton('コピー')
        self.copy.clicked.connect(self.copy_prompt)
        self.copy.hide()
        self.reflect = QPushButton('反映')
        self.reflect.clicked.connect(self.apply_incoming)
        self.reflect.hide()
        self.cancel = QPushButton('やめる')
        self.cancel.clicked.connect(self.reject)
        for button in (self.previous, self.next, self.copy, self.reflect, self.cancel):
            layout.addWidget(button)

    def advance(self):
        try:
            if self.flow.step == 'identity':
                self.flow.identity(self.name.text())
                self.name.setReadOnly(True)
                self.prompt_text.setPlainText(self.flow.prompt())
                self.prompt_text.show()
                self.location.setText(chr(10).join((f'実際の置き場所：{self.flow.destination}', '画像ができたら「反映」を押してください。')))
                self.copy.show()
                self.previous.setEnabled(True)
                self.next.hide()
                self.reflect.show()
                self.cancel.setText('閉じる')
                self.error.clear()
            else:
                self.accept()
        except ValueError as error:
            self.error.setText(str(error))

    def back(self):
        self.flow.back()
        self.name.setReadOnly(False)
        self.prompt_text.hide()
        self.copy.hide()
        self.location.clear()
        self.previous.setEnabled(False)
        self.next.setText('次へ')
        self.next.show()
        self.reflect.hide()
        self.cancel.setText('やめる')

    def apply_incoming(self):
        result = confirm_incoming(self, self.flow.name)
        if result is not None:
            folder, name = result
            if self.on_import is None or self.on_import(folder, name):
                self.result_folder = folder
                self.character_name = name
                self.accept()
            else:
                self.error.setText('設定を保存できません。保存先の権限・空き容量を確認してください。')

    def copy_prompt(self):
        QApplication.clipboard().setText(self.flow.prompt())

    def reject(self):
        self.flow.cancel()
        super().reject()


def confirm_incoming(parent, preferred_name=None):
    """Both entry points use the same validation, confirmation and import."""
    wizard = IncomingDialog(parent, preferred_name=preferred_name)
    try:
        if wizard.exec() == QDialog.DialogCode.Accepted and wizard.result_folder:
            return wizard.result_folder, wizard.character_name
        return None
    finally:
        wizard.deleteLater()


class IncomingDialog(ThemedDialog):
    """Selection does not write; OK validates again and copies."""
    def __init__(self, parent=None, preferred_name=None):
        super().__init__(parent)
        self.result_folder = None
        owner=parent
        while owner is not None and not hasattr(owner,'matching_configs'):
            owner=owner.parentWidget()
        self.owner=owner
        self.targets=QComboBox()
        self.setWindowTitle('キャラを反映')
        layout = QVBoxLayout(self)
        self.choices = QComboBox()
        layout.addWidget(self.choices)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        layout.addWidget(self.targets)
        self.preview = QLabel()
        layout.addWidget(self.preview)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.ok = QPushButton('OK')
        self.ok.clicked.connect(self.apply)
        layout.addWidget(self.ok)
        cancel = QPushButton('やめる')
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.choices.currentIndexChanged.connect(self.inspect)
        try:
            folders = sorted(p for p in incoming_root().iterdir() if p.is_dir())
            for folder in folders:
                self.choices.addItem(folder.name, folder)
            if not folders:
                raise ValueError('置き場所が空です。')
            index = self.choices.findText(preferred_name) if preferred_name else -1
            if index >= 0:
                self.choices.setCurrentIndex(index)
            self.inspect()
        except (OSError, ValueError):
            self.ok.setEnabled(False)
            self.error.setText(f'置き場所が無いか空です：{incoming_root()}')

    @property
    def character_name(self):
        return self.choices.currentText()

    def inspect(self, *args):
        self.ok.setEnabled(False)
        self.preview.clear()
        self.summary.clear()
        try:
            source = self.choices.currentData()
            entries, files = inspect_scenes(source, numbered=True)
            main = source / 'main.png'
            lines = [f'名前：{self.character_name}', 'メインの絵：' + ('あり' if main.is_file() else 'なし（任意）'),
                '13場面がそろっています。', 'OKでコピーして表示します。元のファイルは変えません。']
            if entries['drag_left'].get('mirror'):
                lines.append('左へのドラッグは右の各コマを左右反転します。')
            lines.extend(f'{number:02d} {SCENES[scene]}：確認済み' for number, scene in enumerate(IMPORT_SCENES, 1))
            self.summary.setText(chr(10).join(lines))
            if main.is_file():
                self.preview.setPixmap(QPixmap(str(main)).scaled(
                    240, 240, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            self.targets.clear()
            matches=self.owner.matching_configs(self.character_name) if self.owner else []
            sha=source_sha(source)
            if any(c.source_sha==sha for c in matches):
                self.error.setText('反映済み')
                self.targets.hide()
                return
            for c in matches:
                self.targets.addItem(f'{c.display_name} ({c.id})',c.id)
            self.targets.setVisible(len(matches)>1)
            if len(matches)>1:
                self.targets.setCurrentIndex(-1)
            if matches:
                self.summary.setText(self.summary.text()+chr(10)+f'{self.character_name}の絵を更新します。設定と古い絵は残ります')
            self.error.clear()
            self.ok.setEnabled(True)
        except (OSError, ValueError, TypeError) as error:
            self.error.setText(str(error))

    def apply(self):
        try:
            sha=source_sha(self.choices.currentData())
            matches=self.owner.matching_configs(self.character_name) if self.owner else []
            if any(c.source_sha==sha for c in matches):
                self.error.setText('反映済み'); self.ok.setEnabled(False); return
            if matches and self.targets.currentData() not in {c.id for c in matches}:
                self.error.setText('更新先を選んでください。'); return
            if self.owner:
                self.owner.import_target=self.targets.currentData() if matches else None
            self.result_folder = import_scenes(self.character_name, self.choices.currentData(), numbered=True)
            self.accept()
        except (OSError, ValueError, TypeError) as error:
            self.error.setText(str(error))
