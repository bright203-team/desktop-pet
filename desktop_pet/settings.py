"""One tray and a live, atomic settings editor for all pet windows."""
from dataclasses import replace
import json
import subprocess
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap, QColor
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QFormLayout, QComboBox, QLineEdit, QDoubleSpinBox, QPushButton,
    QSystemTrayIcon, QMenu, QLabel, QCheckBox, QScrollArea, QWidget)
from .character import characters_root, incoming_root
from .character_images import source_sha
from .theme import ThemedDialog, portrait, application_icon
from .startup import StartupShortcut
from .character_dialog import CharacterDialog, confirm_incoming
from .preview import AnimationPreview
from .integration import integration_statuses, CODEX_GUIDE, CLAUDE_GUIDE
from .app import Pet
from .model import config_path, ROOT, Config, load_configs, save_configs, normalize_configs, BUILTIN_IDS


def discover_pets(root=ROOT, home=None):
    result=[]
    for base in (root/'assets'/'pets', (home or Path.home())/'.codex'/'pets', characters_root(home)):
        try:
            result.extend(folder for folder in sorted(base.iterdir()) if (folder/'pet.json').is_file())
        except OSError:
            pass
    return result


def character_label(folder):
    try:
        name=json.loads((Path(folder)/'pet.json').read_text(encoding='utf-8')).get('displayName')
        if isinstance(name,str) and name.strip():
            return name
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return Path(folder).name


class PetManager:
    def __init__(self, backend_factory, root=ROOT, startup=None):
        self.root=Path(root)
        self.startup=startup if startup is not None else StartupShortcut(self.root)
        self.backend_factory=backend_factory
        self.pets={}
        self.configs=[]
        self.dialog=None
        icon=QPixmap(32,32)
        icon.fill(QColor("#eeadbb"))
        self.tray=QSystemTrayIcon(application_icon(self.root, QIcon(icon)))
        self.tray.activated.connect(self.tray_activated)
        self.reload()
        self.tray.show()
        QApplication.instance().aboutToQuit.connect(self.stop)

    def apply(self, configs, save=True):
        # Persist before changing live windows; a failed save leaves the old setup intact.
        configs=normalize_configs([replace(c) for c in configs])
        if save:
            save_configs(config_path(self.root), configs)
        incoming={c.id for c in configs}
        for pet_id in list(self.pets):
            if pet_id not in incoming:
                pet=self.pets.pop(pet_id)
                pet.stop(); pet.close(); pet.deleteLater()
        for config in configs:
            if config.id in self.pets:
                if self.pets[config.id].config != config:
                    self.pets[config.id].reload(config)
            else:
                self.pets[config.id]=Pet(self.backend_factory(),self.root,config,managed=True)
        self.configs=configs
        self.menu=QMenu()
        self.menu.addAction('設定…').triggered.connect(self.open_settings)
        for config in configs:
            action=self.menu.addAction(config.display_name or 'キャラ')
            action.setCheckable(True)
            action.setChecked(config.enabled)
            action.triggered.connect(lambda checked, pet_id=config.id: self.toggle(pet_id,checked))
        self.menu.addAction('設定再読込').triggered.connect(self.reload)
        self.menu.addAction('終了').triggered.connect(QApplication.instance().quit)
        old=self.tray.contextMenu()
        self.tray.setContextMenu(self.menu)
        if old:
            old.deleteLater()
        if self.pets:
            pet=next(iter(self.pets.values()))
            self.tray.setIcon(application_icon(self.root, QIcon(QPixmap.fromImage(pet.sprites.rows['idle'][0]))))

    def toggle(self, pet_id, enabled):
        self.apply([replace(c, enabled=enabled) if c.id==pet_id else c for c in self.configs])
        if self.dialog:
            self.dialog.refresh()

    def reload(self):
        self.apply(load_configs(config_path(self.root)),save=False)
        if self.dialog:
            self.dialog.refresh()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_settings()

    def open_settings(self):
        if self.dialog is None:
            self.dialog=SettingsDialog(self)
        self.dialog.refresh()
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()

    def stop(self):
        for pet in self.pets.values():
            pet.stop(); pet.close()
        self.tray.hide()
        if self.dialog:
            self.dialog.close()


class SettingsDialog(ThemedDialog):
    def __init__(self, manager):
        super().__init__(root=manager.root)
        self.manager=manager
        self.loading=False
        self.previews=[]
        self.incoming_cache={}
        self.setWindowTitle('キャラの設定')
        self.resize(760,520)
        layout=QVBoxLayout(self)
        logo=QLabel()
        logo.setPixmap(QPixmap(str(ROOT/'assets/ui/logo.png')).scaled(180,55,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(logo)
        layout.addWidget(QLabel('デスクトップペット'))
        self.startup_switch=QCheckBox('Windows の起動時に開始する')
        self.startup_switch.toggled.connect(self.toggle_startup)
        layout.addWidget(self.startup_switch)
        body=QHBoxLayout(); layout.addLayout(body,1)
        self.list=QListWidget()
        self.list.setFixedWidth(265)
        body.addWidget(self.list)
        buttons=QHBoxLayout()
        for label, handler in (('キャラを追加',self.create_character),('反映',self.apply_incoming),('削除',self.remove_pet)):
            button=QPushButton(label)
            if handler == self.apply_incoming:
                self.reflect_button=button; button.setProperty('primary',True)
            if handler == self.remove_pet:
                self.remove_button=button
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.banner=QLabel("新しい絵が届いています"); self.banner.setObjectName("banner")
        layout.insertWidget(2,self.banner)
        form=QFormLayout()
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True)
        content=QWidget(); content.setObjectName('details'); content.setLayout(form); self.scroll.setWidget(content)
        body.addWidget(self.scroll,1)
        self.large_preview=QLabel(); form.addRow(self.large_preview)
        self.folder=QComboBox()
        self.name=QLineEdit()
        self.scale=QDoubleSpinBox()
        self.scale.setRange(.05,10); self.scale.setSingleStep(.1)
        self.movement=QComboBox()
        self.source=QComboBox()
        self.caption_color=QComboBox()
        for label,value in (('ピンク','pink'),('ラベンダー','lavender'),('ミント','mint'),('水色','blue'),('クリーム','cream')):
            self.caption_color.addItem(label,value)
        for label,value in (('Claude','claude'),('ChatGPT','chatgpt'),('なし','none')):
            self.movement.addItem(label,value)
        for label,value in (('Claude Code','claude-code'),('Codex','codex'),('なし','none')):
            self.source.addItem(label,value)
        for label,field in (('キャラ',self.folder),('表示名',self.name),('倍率',self.scale),('移動範囲',self.movement),('連動元',self.source),('文字の色',self.caption_color)):
            form.addRow(label,field)
        advanced=QPushButton('場面の動き・切り替え…')
        advanced.clicked.connect(self.scene_settings)
        form.addRow(advanced)
        preview=QPushButton('アニメのプレビュー…')
        preview.clicked.connect(self.animation_preview)
        form.addRow(preview)
        self.link_status_labels=[]
        self.link_help_buttons=[]
        for index,label in enumerate(('Claude Code','Codex Windows','Codex WSL')):
            status=QLabel(); status.setWordWrap(True)
            form.addRow(label,status)
            help_button=QPushButton('確認手順…')
            help_button.clicked.connect(lambda checked=False,i=index: self.integration_help(i))
            form.addRow(help_button)
            self.link_status_labels.append(status)
            self.link_help_buttons.append(help_button)
        self.link_button=QPushButton('連携テスト')
        self.link_button.clicked.connect(self.test_integration)
        form.addRow(self.link_button)
        self.link_hint=QLabel('選択したキャラで作業中 → 返事待ち → 完了を各3秒表示します。終了後は元の状態（途中の実通知があれば最新）に戻ります。キャラを表示し、表示先のアプリを開いてください。連携テストは見た目の確認です。実際の通知の受信は上の時刻で確かめてください。')
        self.link_hint.setWordWrap(True)
        form.addRow(self.link_hint)
        buttons.removeWidget(self.remove_button)
        form.addRow(self.remove_button)
        self.error=QLabel()
        layout.addWidget(self.error)
        self.list.currentRowChanged.connect(self.select)
        self.name.textEdited.connect(self.changed)
        self.scale.valueChanged.connect(self.changed)
        for field in (self.folder,self.movement,self.source,self.caption_color):
            field.currentIndexChanged.connect(self.changed)
        self.refresh()
        self.incoming_timer=QTimer(self)
        self.incoming_timer.setInterval(2000)
        self.incoming_timer.timeout.connect(self.update_incoming_banner)
        self.incoming_timer.start()
        self.link_timer=QTimer(self)
        self.link_timer.setInterval(1000)
        self.link_timer.timeout.connect(self.refresh_integrations)
        self.link_timer.start()
        self.refresh_integrations()

    def refresh_integrations(self):
        if not self.isVisible() and self.link_status_labels[0].text():
            return
        for status,label,button in zip(integration_statuses(self.manager.root),self.link_status_labels,self.link_help_buttons):
            label.setText(status.text+('\n'+status.note if status.note else ''))
            label.setToolTip(status.note)
            button.setVisible(status.registered and status.last_received is None)
        active=any(p.link_test.active for p in self.manager.pets.values())
        self.link_button.setEnabled(not active and self.list.currentRow()>=0)
        self.link_button.setText('連携テスト中…' if active else '連携テスト')

    def integration_help(self, index):
        dialog=ThemedDialog(self,root=self.manager.root)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle('連携の確認手順')
        layout=QVBoxLayout(dialog)
        text=QLabel(CLAUDE_GUIDE if index==0 else CODEX_GUIDE)
        text.setWordWrap(True); layout.addWidget(text)
        close=QPushButton('閉じる'); close.clicked.connect(dialog.close); layout.addWidget(close)
        dialog.resize(480,260)
        dialog.show()

    def test_integration(self):
        index=self.list.currentRow()
        if 0<=index<len(self.manager.configs):
            pet=self.manager.pets.get(self.manager.configs[index].id)
            if pet:
                pet.start_link_test()
                self.refresh_integrations()

    def refresh(self):
        self.refresh_startup()
        index=max(0,self.list.currentRow())
        self.loading=True
        self.list.clear()
        self.switches=[]
        self.row_labels=[]
        for c in self.manager.configs:
            item=QListWidgetItem()
            item.setData(Qt.ItemDataRole.AccessibleTextRole,c.display_name or 'キャラ')
            self.list.addItem(item)
            row=QWidget(); line=QHBoxLayout(row); line.setContentsMargins(4,4,4,4)
            face=QLabel(); face.setPixmap(portrait(c,self.manager.root)); line.addWidget(face)
            label=QLabel(c.display_name or 'キャラ'); line.addWidget(label,1)
            self.row_labels.append(label)
            switch=QCheckBox('表示' if c.enabled else '非表示'); switch.setChecked(c.enabled)
            switch.setAccessibleName((c.display_name or 'キャラ')+'の表示')
            switch.toggled.connect(lambda checked, pet_id=c.id: self.toggle_character(pet_id,checked))
            line.addWidget(switch); self.switches.append(switch)
            item.setSizeHint(row.sizeHint()); self.list.setItemWidget(item,row)
        pending=self.pending_incoming()
        self.banner.setVisible(pending); self.reflect_button.setVisible(pending)
        self.loading=False
        self.list.setCurrentRow(min(index,len(self.manager.configs)-1))
        self.select(self.list.currentRow())
        self.refresh_integrations()

    def refresh_startup(self):
        try:
            enabled=self.manager.startup.enabled()
        except OSError as error:
            self.startup_switch.setEnabled(False)
            self.error.setText(f'起動時の設定を確認できませんでした：{error}')
            return
        self.startup_switch.setEnabled(True)
        self.startup_switch.blockSignals(True)
        self.startup_switch.setChecked(enabled)
        self.startup_switch.blockSignals(False)

    def toggle_startup(self, enabled):
        previous=not enabled
        try:
            self.manager.startup.set_enabled(enabled)
        except (OSError, subprocess.SubprocessError) as error:
            self.startup_switch.blockSignals(True)
            self.startup_switch.setChecked(previous)
            self.startup_switch.blockSignals(False)
            self.error.setText(f'起動時の設定を変更できませんでした：{error}')
        else:
            self.error.clear()

    def select(self, index):
        if self.loading:
            return
        self.loading=True
        valid=0<=index<len(self.manager.configs)
        for field in (self.folder,self.name,self.scale,self.movement,self.source,self.caption_color):
            field.setEnabled(valid)
        fixed=valid and self.manager.configs[index].id in BUILTIN_IDS
        self.remove_button.setVisible(valid and not fixed)
        self.remove_button.setEnabled(valid and not fixed)
        self.folder.setEnabled(valid and not fixed)
        if valid:
            config=self.manager.configs[index]
            self.folder.clear()
            folders=[str(p) for p in discover_pets(self.manager.root)]
            if config.pet_folder not in folders:
                folders.insert(0,config.pet_folder)
            for folder in folders:
                self.folder.addItem(character_label(folder),folder)
            self.folder.setCurrentIndex(self.folder.findData(config.pet_folder))
            self.large_preview.setPixmap(portrait(config,self.manager.root,150,False))
            self.name.setText(config.display_name)
            self.scale.setValue(config.scale)
            self.movement.setCurrentIndex(self.movement.findData(config.movement))
            self.source.setCurrentIndex(self.source.findData(config.source))
            self.caption_color.setCurrentIndex(self.caption_color.findData(config.caption_color))
        self.loading=False

    def animation_preview(self):
        index=self.list.currentRow()
        if not 0<=index<len(self.manager.configs):
            return
        config=self.manager.configs[index]
        def save(updated):
            configs=[replace(item,scene_speeds=dict(updated.scene_speeds))
                     if item.id==config.id else item for item in self.manager.configs]
            return self.commit(configs)
        def reload_images():
            for item in self.manager.configs:
                if item.pet_folder==config.pet_folder and item.id in self.manager.pets:
                    self.manager.pets[item.id].reload(item,force_sprites=True)
        dialog=AnimationPreview(config,self.manager.root,save,reload_images,self)
        self.previews.append(dialog)
        dialog.destroyed.connect(lambda: self.previews.remove(dialog) if dialog in self.previews else None)
        dialog.show()

    def closeEvent(self, event):
        for pet in self.manager.pets.values():
            pet.link_test.cancel()
        for dialog in list(self.previews):
            dialog.close()
        super().closeEvent(event)

    def scene_settings(self):
        index=self.list.currentRow()
        if index>=0:
            dialog=SceneSettings(self.manager.configs[index],self)
            if dialog.exec()==QDialog.DialogCode.Accepted:
                configs=list(self.manager.configs)
                configs[index]=dialog.config
                self.commit(configs)

    def commit(self, configs):
        try:
            self.manager.apply(configs)
            self.error.clear()
            return True
        except OSError:
            self.error.setText('設定を保存できません。保存先の権限・空き容量を確認してください。')
            return False

    def changed(self, *args):
        index=self.list.currentRow()
        if self.loading or index<0:
            return
        configs=list(self.manager.configs)
        configs[index]=replace(configs[index],pet_folder=(configs[index].pet_folder if configs[index].id in BUILTIN_IDS else self.folder.currentData()),display_name=self.name.text(),
            scale=self.scale.value(),movement=self.movement.currentData(),source=self.source.currentData(),caption_color=self.caption_color.currentData())
        if self.commit(configs):
            label=configs[index].display_name or 'キャラ'
            self.list.item(index).setData(Qt.ItemDataRole.AccessibleTextRole,label)
            self.row_labels[index].setText(label)
            self.switches[index].setAccessibleName(label+'の表示')

    def create_character(self):
        wizard=CharacterDialog(self, on_import=self.add_imported_character)
        try:
            wizard.exec()
        finally:
            wizard.deleteLater()

    def add_imported_character(self, folder, name):
        sha=source_sha(folder, stored=True)
        target=getattr(self, 'import_target', None)
        config=Config(id=uuid4().hex,display_name=name,pet_folder=str(folder),incoming_name=name,source_sha=sha)
        configs=[replace(c,pet_folder=str(folder),incoming_name=name,source_sha=sha) if c.id==target else c
                 for c in self.manager.configs] if target else self.manager.configs+[config]
        if self.commit(configs):
            self.refresh()
            self.list.setCurrentRow(next((i for i,c in enumerate(self.manager.configs) if c.id==target),len(self.manager.configs)-1))
            return True
        return False

    def toggle_character(self, pet_id, enabled):
        index=self.list.currentRow()
        focused=QApplication.focusWidget() in self.switches
        if self.commit([replace(c,enabled=enabled) if c.id==pet_id else c for c in self.manager.configs]):
            self.refresh(); self.list.setCurrentRow(index)
            if focused:
                for i,c in enumerate(self.manager.configs):
                    if c.id==pet_id:
                        self.switches[i].setFocus()

    def update_incoming_banner(self):
        if self.isVisible():
            pending=self.pending_incoming()
            self.banner.setVisible(pending); self.reflect_button.setVisible(pending)

    def pending_incoming(self):
        # Poll metadata only; unchanged valid and invalid folders reuse the
        # previous validation/hash. Config matches are checked every time.
        try:
            folders=list(incoming_root().iterdir())
            self.incoming_cache={p:v for p,v in self.incoming_cache.items() if p in folders}
            for folder in folders:
                try:
                    signature=[]
                    for path in sorted(folder.iterdir()):
                        stat=path.stat()
                        signature.append((path.name,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,stat.st_mode))
                    signature=tuple(signature)
                    cached=self.incoming_cache.get(folder)
                    if cached is None or cached[0]!=signature:
                        try:
                            sha=source_sha(folder)
                        except (OSError,ValueError,TypeError):
                            sha=None
                        self.incoming_cache[folder]=(signature,sha)
                    else:
                        sha=cached[1]
                    if sha is None:
                        continue
                    if not any(c.source_sha==sha for c in self.matching_configs(folder.name)):
                        return True
                except (OSError,ValueError,TypeError):
                    continue
        except OSError:
            self.incoming_cache.clear()
        return False

    def matching_configs(self, name):
        fixed={'フラン':'default','シフォン':'chiffon'}.get(name)
        if fixed:
            return [c for c in self.manager.configs if c.id==fixed]
        return [c for c in self.manager.configs if c.incoming_name==name or
                (not c.incoming_name and c.display_name==name)]

    def apply_incoming(self):
        result=confirm_incoming(self)
        if result is not None:
            self.add_imported_character(*result)

    def remove_pet(self):
        index=self.list.currentRow()
        if 0<=index<len(self.manager.configs) and self.manager.configs[index].id not in BUILTIN_IDS and self.commit([c for i,c in enumerate(self.manager.configs) if i!=index]):
            self.refresh()


class SceneSettings(ThemedDialog):
    """Keep infrequent animation choices in a scrollable Japanese editor."""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config=config
        self.setWindowTitle('場面の動き・切り替え')
        self.resize(500,600)
        layout=QVBoxLayout(self)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        content=QWidget()
        form=QFormLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.fields={}
        for key,label in (('idle_min_seconds','待機の変化：最短（秒）'),('idle_max_seconds','待機の変化：最長（秒）'),
                          ('sleep_seconds','寝始めるまで（秒）'),('offline_seconds','未接続が続く時間（秒）'),
                          ('review_seconds','完了を表示する時間（秒）'),('idle_seconds','返事待ちから待機まで（秒）')):
            field=QDoubleSpinBox(); field.setRange(0,100000); field.setValue(getattr(config,key))
            self.fields[key]=field
            form.addRow(label,field)
        order=QComboBox(); order.addItem('ランダム（連続で同じ動きにしない）','random'); order.addItem('順番に切り替える','sequential')
        order.setCurrentIndex(order.findData(config.idle_order))
        self.fields['idle_order']=order; form.addRow('待機の順番',order)
        for key,label in (('offline_enabled','Windowsの未接続状態で布団に入る'),('hover_repeat','マウスが乗っている間くり返す'),
                          ('click_restart','連打でクリック演出を最初から再生'),('scene_gaze','新形式でも視線画像があれば使う'),
                          ('strong_model_aura','強いモデルのときのオーラ')):
            field=QCheckBox(); field.setChecked(getattr(config,key)); self.fields[key]=field
            form.addRow(label,field)
        self.priorities=[]
        labels={'drag':'ドラッグ中','click':'クリック','offline':'繋がらない','waiting':'返事・許可待ち',
                'working':'作業中','done':'作業完了','hover':'マウスオーバー','idle':'待機'}
        for i,key in enumerate(config.scene_priority.split(',')):
            field=QComboBox()
            for value,label in labels.items(): field.addItem(label,value)
            field.setCurrentIndex(field.findData(key)); self.priorities.append(field)
            form.addRow(f'優先順位 {i+1}（上ほど優先）',field)
        self.error=QLabel(); layout.addWidget(self.error)
        save=QPushButton('保存'); save.clicked.connect(self.save); layout.addWidget(save)

    def save(self):
        priority=[field.currentData() for field in self.priorities]
        if len(set(priority))!=8:
            self.error.setText('優先順位は同じ場面を重複させずに選んでください。'); return
        values={key: (field.isChecked() if isinstance(field,QCheckBox) else field.currentData()
                     if isinstance(field,QComboBox) else field.value()) for key,field in self.fields.items()}
        values['scene_priority']=','.join(priority)
        self.config=replace(self.config,**values)
        self.accept()
