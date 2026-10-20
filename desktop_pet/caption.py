"""Cached glyph rasters with clock-driven reveal and bounded wave motion."""
import math
from PySide6.QtCore import Qt
from PySide6.QtGui import (QFont, QFontMetricsF, QPainterPath, QPainter,
                          QPen, QColor, QPixmap, QRegion)
from .model import CAPTION_COLORS

HEIGHT = 48
# Share the 10Hz clock so each reveal gets its own displayed frame.
FRAME_SECONDS = .1
REVEAL_SECONDS = .1


class Caption:
    def __init__(self, text, width, height=HEIGHT, color='pink', started=0):
        self.width, self.height, self.started = width, height, started
        font=QFont()
        font.setFamilies(['UD Digi Kyokasho NK','Noto Sans JP','Yu Gothic UI'])
        font.setPixelSize(20)
        font.setWeight(QFont.Weight.Bold)
        metrics=QFontMetricsF(font)
        self.text=(metrics.elidedText(text.replace('…','...'),Qt.TextElideMode.ElideRight,max(0,width-20))
                   if text and width>=20 else '')
        letters=self.text.replace('…','...')
        advances=[metrics.horizontalAdvance(c) for c in letters]
        # Kerning in elidedText measures a whole string; independent glyphs
        # use individual advances, which can be wider on Windows fonts.
        if sum(advances)>max(0,width-20):
            prefix=letters[:-3] if letters.endswith('...') else letters
            while prefix and sum(metrics.horizontalAdvance(c) for c in prefix+'...')>width-20:
                prefix=prefix[:-1]
            letters=prefix+'...' if metrics.horizontalAdvance('.')*3<=width-20 else ''
            self.text=prefix+'…' if letters else ''
            advances=[metrics.horizontalAdvance(c) for c in letters]
        x=(width-sum(advances))/2
        self.glyphs=[]
        self.alpha_images=[]
        for char,advance in zip(letters,advances):
            path=QPainterPath()
            path.addText(0,0,font,char)
            bounds=path.boundingRect()
            pix=QPixmap(max(1,math.ceil(bounds.width())+12),max(1,math.ceil(metrics.height())+12))
            pix.fill(Qt.GlobalColor.transparent)
            # Common baseline preserves punctuation and Latin descenders.
            path.translate(6-bounds.left(),6+metrics.ascent())
            p=QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            for fill,stroke,offset in ((QColor(70,40,60,150),7,2),(QColor('#ffffff'),4,0)):
                pen=QPen(fill,stroke)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(fill)
                p.drawPath(path.translated(0,offset))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(CAPTION_COLORS.get(color,CAPTION_COLORS['pink'])))
            p.drawPath(path)
            p.end()
            self.glyphs.append((pix,round(x+bounds.left()-6)))
            self.alpha_images.append(pix.toImage())
            x+=advance

    def layout(self, now, effects=True):
        elapsed=max(0,now-self.started)
        count=min(len(self.glyphs),1+int((elapsed+1e-9)/REVEAL_SECONDS)) if effects else len(self.glyphs)
        result=[]
        for i,(pix,x) in enumerate(self.glyphs[:count]):
            room=max(0,(self.height-pix.height())/2)
            y=round(room-min(3,room)*math.sin(elapsed*2*math.pi/.8-i*.65)) if effects else round(room)
            result.append((i,x,y))
        return result

    def draw(self, painter, frame):
        for i,x,y in frame:
            painter.drawPixmap(x,y,self.glyphs[i][0])

    def hit(self, frame, x, y):
        # Cached per-glyph alpha, tested only when input needs a hit result.
        return any(0 <= x-gx < self.alpha_images[i].width()
                   and 0 <= y-gy < self.alpha_images[i].height()
                   and self.alpha_images[i].pixelColor(x-gx,y-gy).alpha() > 0
                   for i,gx,gy in frame)

    def render(self, now, effects=True):
        """Static snapshot helper; animated widgets draw cached glyphs directly."""
        pix=QPixmap(self.width,self.height)
        pix.fill(Qt.GlobalColor.transparent)
        p=QPainter(pix)
        self.draw(p,self.layout(now,effects))
        p.end()
        return pix,QRegion(pix.mask()),self.text


def caption(text, width, height=40, color='pink'):
    return Caption(text,width,height,color).render(0,False)
