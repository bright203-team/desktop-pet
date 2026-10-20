"""Qt overlay; native API is injected for headless tests."""
import math
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPoint, QLockFile
from PySide6.QtGui import QPainter, QPixmap, QIcon
from PySide6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu
from .model import config_path, ROOT, Config, Controller, durations, position, ratios, load_position, save_position, gaze_index, position_path
from .sprites import Sprites
from .theme import application_icon
from .scene_runtime import SceneController
from .state import StateWatcher, NoStateWatcher, state_path
from .caption import Caption, HEIGHT, FRAME_SECONDS
from .aura import AuraWindow

class InstanceLock:
    def __init__(self, path):
        self.lock = QLockFile(str(path))
        self.lock.setStaleLockTime(0)
    def acquire(self):
        return self.lock.tryLock(0)
    def release(self):
        self.lock.unlock()

class Pet(QWidget):
    def __init__(self, backend, root=ROOT, config=None, managed=False):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.root=root
        self.backend=backend
        self.managed=managed
        self.config=config or Config.load(config_path(root))
        self.controller=Controller(backend,self.config)
        self.scenes=SceneController(self.config, clock=lambda: time.monotonic())
        self.controller.scene_runtime=self.scenes
        self.ratio=load_position(position_path(root,self.config.id),(self.config.initial_x,self.config.initial_y))
        self.frame_index=0
        self.cycle=None
        self.deadline=0
        self.press=None
        self.moved=False
        self.hovering=False
        self.owner=None
        self.scaled_frames={}
        self.frame_pixmaps={}
        self.last_paint=None
        self.aura=AuraWindow(self)
        self.reload(self.config)
        self.configure_watcher()
        self.geometry_at=0
        self.state_at=0
        self.timer=QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.wake)
        self.timer.start(0)
        self.native_events=getattr(self.backend,'watch',lambda callback: False)(self.native_changed)
        QApplication.instance().aboutToQuit.connect(self.stop)
        self.tray=None
        if not managed:
            self.tray=QSystemTrayIcon(application_icon(root, QIcon(QPixmap.fromImage(self.sprites.rows['idle'][0]))),self)
            menu=QMenu(self)
            menu.addAction('表示ON/OFF').triggered.connect(self.toggle)
            menu.addAction('設定再読込').triggered.connect(self.reload)
            menu.addAction('終了').triggered.connect(QApplication.instance().quit)
            self.tray.setContextMenu(menu)
            self.tray.show()

    def configure_watcher(self):
        self.state_watcher=(NoStateWatcher() if self.config.source=='none' else
                            StateWatcher(self.controller,state_path(self.config.source),read_interval=0.25))

    def reload(self, config=None, force_sprites=False):
        previous=getattr(self,'config',None)
        self.config=config if isinstance(config,Config) else Config.load(config_path(self.root))
        self.controller.config=self.config
        self.controller.enabled=self.config.enabled
        folder=Path(self.config.pet_folder).expanduser()
        self.sprite_size=(round(192*self.config.scale),round(208*self.config.scale))
        if force_sprites or not hasattr(self,'sprites') or previous.pet_folder!=self.config.pet_folder or previous.scale!=self.config.scale:
            self.sprites=Sprites(folder if folder.is_absolute() else self.root/folder, size=self.sprite_size)
        self.scenes.config=self.config
        if previous != self.config:
            self.scenes.activity()
        self.resize(self.sprite_size[0],self.sprite_size[1]+(HEIGHT if self.config.bubble else 0))
        self.aura.reload()
        self.setWindowOpacity(self.config.opacity)
        self.cycle=None
        self.scaled_frames={}
        self.frame_pixmaps={}
        self.last_paint=None
        self.caption_key=None
        self.owner=None
        self.geometry_at=0
        if hasattr(self,'state_watcher') and previous.source!=self.config.source:
            self.controller.model=''
            self.controller.set_state('idle')
            self.configure_watcher()
        if hasattr(self,'timer'):
            self.timer.start(0)

    def stop(self):
        self.timer.stop()
        self.aura.hide()
        getattr(self.backend,'unwatch',lambda: None)()

    def hideEvent(self, event):
        self.aura.hide()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.aura.close()
        super().closeEvent(event)

    def moveEvent(self, event):
        if self.aura.isVisible():
            self.aura.follow_pet()
        super().moveEvent(event)

    def native_changed(self):
        # Coalesce event bursts on the installing Qt message-loop thread.
        self.geometry_at=0
        self.foreground_at=0
        self.aura.stacking=None
        self.timer.start(0)

    def wake(self):
        self.tick(refresh=False)

    def gaze_enabled(self):
        return ((not self.sprites.scene_format or self.config.scene_gaze)
                and self.controller.state == 'idle'
                and self.scenes.scene == 'idle_blink'
                and not self.sprites.expressions.get(self.controller.expression)
                and bool(self.sprites.gaze) and self.config.gaze_radius > 0)

    def schedule(self, now, visible):
        deadlines=[self.geometry_at,self.state_at,getattr(self,'effects_at',0)/1000]
        if self.state_watcher.phase in ('review','complete'):
            deadlines.append(getattr(self,'foreground_at',0))
        if visible:
            if self.aura.isVisible() and math.isfinite(self.aura.next_frame):
                deadlines.append(self.aura.next_frame)
            if self.scenes.next_change > now:
                deadlines.append(self.scenes.next_change)
            if getattr(self,'effects',True):
                deadlines.append(self.deadline/1000)
                if getattr(self,'caption_text',''):
                    deadlines.append(self.caption_at)
                if self.gaze_enabled():
                    deadlines.append(getattr(self,'cursor_at',0)/1000)
            elif self.controller.state in ('jumping','waving'):
                deadlines.append(self.cycle_end/1000)
        delay=max(1,math.ceil((min(deadlines)-now)*1000))
        self.timer.start(delay)

    def toggle(self):
        self.controller.enabled=not self.controller.enabled
        self.tick()

    def set_state(self, state, expression='normal', message=''):
        """Public seam for the later hooks/state-file integration."""
        self.controller.set_state(state,expression,message)
        self.cycle=None
        if hasattr(self,'timer'):
            self.timer.start(0)

    def tick(self, refresh=True):
        now_seconds=time.monotonic()
        if refresh or now_seconds>=self.geometry_at:
            visible=self.controller.poll()
            # Hooks give immediate movement; periodic discovery also handles restarts.
            self.native_events=getattr(self.backend,'events_available',self.native_events)
            self.geometry_at=now_seconds+(2 if self.native_events else 0.02)
        else:
            t=self.controller.target
            visible=bool(self.controller.enabled and t and t.visible and not t.minimized and t.rect[2]>=self.config.min_width and t.rect[3]>=self.config.min_height)
        target=self.controller.target
        if now_seconds>=getattr(self,'foreground_at',0):
            self.cached_foreground=bool(target and target.handle and getattr(self.backend,'foreground',lambda handle: False)(target.handle))
            self.foreground_at=now_seconds+0.25
        foreground=getattr(self,'cached_foreground',False)
        if refresh or now_seconds>=self.state_at:
            self.state_at=now_seconds+0.25
            self.state_watcher.poll(foreground)
        if now_seconds>=getattr(self,'connection_at',0):
            self.connected=getattr(self.backend,'connected',lambda: True)()
            self.connection_at=now_seconds+2
        if now_seconds*1000>=getattr(self,'effects_at',0):
            self.effects=self.backend.animations()
            self.effects_at=now_seconds*1000+2000
        if not visible:
            self.aura.sync(now_seconds,False)
            self.hide()
            self.schedule(now_seconds,False)
            return
        target=self.controller.target
        if self.owner!=target.handle:
            self.attach_target(target)
            self.owner=target.handle
        if not self.controller.dragging:
            destination=position(target.rect,(self.width(),self.height()),self.ratio)
            if destination!=(self.x(),self.y()):
                self.move(*destination)
        if not self.isVisible():
            self.show()
            self.attach_target(target)
        state=self.scenes.update(self.controller,getattr(self,'connected',True),self.hovering)
        if not self.sprites.scene_format and self.controller.base_state == 'failed' and state == 'working':
            state='offline'  # Keep the original Codex Pets failed row.
        sequence=self.sprites.for_scene(state,self.controller.expression)
        now=time.monotonic()*1000
        key=(state,self.controller.expression,self.controller.revision)
        if self.cycle!=key:
            self.cycle=key
            self.frame_index=0
            self.frame_times=self.sprites.scene_durations(state,self.config.scene_speed(state))
            self.deadline=now+self.frame_times[0]
            self.cycle_end=now+sum(self.frame_times)
        animate=self.effects
        if animate and now>=self.deadline:
            self.frame_index+=1
            if self.frame_index>=len(sequence):
                self.frame_index=0
                self.scenes.finish(state)
                if not self.sprites.scene_format and self.controller.state in ('jumping','waving'):
                    self.controller.state='idle'
                if self.scenes.held:
                    self.frame_index=len(sequence)-1
                elif self.scenes.update(self.controller,self.connected,self.hovering)!=state:
                    self.cycle=None
            self.deadline=(float('inf') if self.scenes.held else now+self.frame_times[self.frame_index])
        if not animate:
            self.frame_index=0
            if now>=self.cycle_end:
                self.scenes.finish(state)
                if not self.sprites.scene_format and self.controller.state in ('jumping','waving'):
                    self.controller.state='idle'
                if self.scenes.update(self.controller,self.connected,self.hovering)!=state:
                    self.cycle=None
        self.image=sequence[self.frame_index]
        self.aura.sync(now_seconds,True)
        if animate and state=='idle_blink' and self.gaze_enabled():
            if now>=getattr(self,'cursor_at',0):
                self.cached_cursor=self.backend.cursor()
                self.cursor_at=now+150
            cursor=self.cached_cursor
            dx=cursor[0]-(self.x()+self.sprite_size[0]/2)
            dy=cursor[1]-(self.y()+self.bubble_height+self.sprite_size[1]/2)
            if math.hypot(dx,dy)<=self.config.gaze_radius:
                self.image=self.sprites.gaze[gaze_index(dx,dy)]
        self.update_caption(now_seconds)
        paint_key=(self.image.cacheKey(),self.controller.message,self.config.pc_label,self.config.bubble,self.caption_frame,self.config.caption_color)
        if paint_key!=self.last_paint:
            self.last_paint=paint_key
            self.update()
        self.schedule(now_seconds,True)

    def attach_target(self, target):
        if self.config.movement == 'none':
            self.backend.topmost(int(self.winId()))
        else:
            self.backend.attach(int(self.winId()),target.handle)

    @property
    def bubble_height(self):
        return HEIGHT if self.config.bubble else 0

    def scaled_image(self):
        if (self.image.width(),self.image.height()) == self.sprite_size:
            return self.image
        key=self.image.cacheKey()
        if key not in self.scaled_frames:
            self.scaled_frames[key]=self.image.scaled(*self.sprite_size,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        return self.scaled_frames[key]

    def update_caption(self, now=None):
        now=time.monotonic() if now is None else now
        # Interaction animations keep the idle caption without restarting glyphs.
        waiting=(self.config.source!='none' and not self.controller.message
                 and self.controller.state in ('idle','jumping','waving'))
        text=(self.controller.message or ('待ち…' if waiting else self.config.pc_label)) if self.config.bubble else ''
        key=(text,self.width(),self.bubble_height,self.config.caption_color)
        if key!=self.caption_key:
            self.caption_key=key
            self.caption_animation=Caption(text,self.width(),max(1,self.bubble_height),self.config.caption_color,now)
            self.caption_frame=None
            self.caption_text=self.caption_animation.text
        step=math.floor(max(0,now-self.caption_animation.started)/FRAME_SECONDS+1e-9)
        sampled=self.caption_animation.started+step*FRAME_SECONDS
        self.caption_at=self.caption_animation.started+(step+1)*FRAME_SECONDS
        frame=tuple(self.caption_animation.layout(sampled,getattr(self,'effects',True)))
        if frame!=self.caption_frame:
            self.caption_frame=frame

    @staticmethod
    def opaque_at(image, x, y):
        return (0 <= x < image.width() and 0 <= y < image.height()
                and image.pixelColor(x,y).alpha() > 0)

    def hit(self, x, y):
        # Windows layered windows pass zero-alpha pixels through natively.
        # Use the same painted pixels for Qt interaction, without setMask.
        if x < 0 or y < 0:
            return None
        x,y=int(x),int(y)
        if self.config.bubble and getattr(self,'caption_frame',None) and self.caption_animation.hit(self.caption_frame,x,y):
            return 'bubble'
        if hasattr(self,'image') and self.opaque_at(self.scaled_image(),x,y-self.bubble_height):
            return 'pet'
        return None

    def paintEvent(self,event):
        if not hasattr(self,'image'):
            return
        p=QPainter(self)
        if self.config.bubble:
            self.caption_animation.draw(p,self.caption_frame)
        image=self.scaled_image()
        key=image.cacheKey()
        if key not in self.frame_pixmaps:
            self.frame_pixmaps[key]=QPixmap.fromImage(image)
        p.drawPixmap(0,self.bubble_height,self.frame_pixmaps[key])

    def enterEvent(self,event):
        if hasattr(self,'image'):
            point=self.mapFromGlobal(QPoint(*self.backend.cursor()))
            self.track_hover(point.x(),point.y())

    def track_hover(self, x, y):
        hovering=self.hit(x,y)=='pet'
        if hovering and self.scenes.held:
            self.scenes.activity()
        if hovering and not self.hovering:
            self.scenes.hover()
            if not self.sprites.scene_format:
                self.controller.hover()
        self.hovering=hovering
        self.timer.start(0)

    def leaveEvent(self,event):
        self.hovering=False

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:
            return
        hit=self.hit(event.position().x(),event.position().y())
        if hit=='bubble' and self.controller.target and self.controller.target.handle:
            self.backend.activate(self.controller.target.handle)
        elif hit=='pet':
            self.press=event.globalPosition().toPoint()
            self.offset=event.position().toPoint()
            self.moved=False

    def mouseMoveEvent(self,event):
        if self.press is None:
            self.track_hover(event.position().x(),event.position().y())
            return
        if not self.controller.target:
            return
        cursor=event.globalPosition().toPoint()
        if not self.moved and (cursor-self.press).manhattanLength()<QApplication.startDragDistance():
            return
        self.moved=True
        previous=self.x()
        proposed=cursor-self.offset
        ratio=ratios(self.controller.target.rect,(self.width(),self.height()),(proposed.x(),proposed.y()))
        self.move(*position(self.controller.target.rect,(self.width(),self.height()),ratio))
        self.ratio=ratio
        self.scenes.drag(self.x()-previous)
        if self.sprites.scene_format:
            self.controller.dragging=True
        else:
            self.controller.drag(previous,self.x())
        self.timer.start(0)

    def mouseReleaseEvent(self,event):
        if self.press is not None:
            if self.moved:
                self.scenes.release()
            elif self.scenes.click():
                self.cycle=None
            if self.sprites.scene_format:
                self.controller.dragging=False
            else:
                self.controller.release(self.moved)
            if self.moved:
                save_position(position_path(self.root,self.config.id),self.ratio)
            self.press=None
            self.timer.start(0)
