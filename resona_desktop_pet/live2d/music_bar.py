"""Inline music controls sharing the existing chat rectangle."""
from concurrent.futures import Future
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QRectF, QPointF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QSlider, QListWidget, QListWidgetItem, QMenu

MODES = {'sequence':'顺序播放', 'list_loop':'列表循环', 'single_loop':'单曲循环', 'shuffle':'随机播放'}

def icon(kind, color='#f3f4f6'):
    pix=QPixmap(48,48);pix.fill(Qt.GlobalColor.transparent)
    p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.scale(2,2)
    p.setPen(QPen(QColor(color),1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin));p.setBrush(QColor(color))
    if kind in ('play','next','previous'):
        if kind=='previous':p.translate(24,0);p.scale(-1,1)
        shape=QPainterPath();shape.moveTo(8,5);shape.lineTo(18,12);shape.lineTo(8,19);shape.closeSubpath();p.drawPath(shape)
        if kind!='play':p.drawLine(20,5,20,19)
    elif kind=='pause':
        p.drawRoundedRect(QRectF(7,5,3,14),.5,.5);p.drawRoundedRect(QRectF(15,5,3,14),.5,.5)
    elif kind=='close':p.drawLine(7,7,17,17);p.drawLine(17,7,7,17)
    elif kind=='back':p.drawLine(15,6,9,12);p.drawLine(9,12,15,18)
    elif kind=='list':
        for y in (6,12,18):p.drawPoint(4,y);p.drawLine(9,y,20,y)
    elif kind=='shuffle':
        p.setBrush(Qt.BrushStyle.NoBrush)
        for points in [[(4,6),(8,6),(16,18),(21,18)],[(4,18),(8,18),(16,6),(21,6)]]:
            shape=QPainterPath();shape.moveTo(*points[0])
            for point in points[1:]:shape.lineTo(*point)
            p.drawPath(shape)
        for y in (6,18):p.drawLine(18,y-3,21,y);p.drawLine(18,y+3,21,y)
    else:
        p.setBrush(Qt.BrushStyle.NoBrush)
        for points in [[(4,10),(4,6),(20,6),(17,3)],[(20,14),(20,18),(4,18),(7,21)]]:
            shape=QPainterPath();shape.moveTo(*points[0])
            for point in points[1:]:shape.lineTo(*point)
            p.drawPath(shape)
        p.drawLine(20,6,17,9);p.drawLine(4,18,7,15)
        if kind=='single_loop':p.drawText(QRectF(8,7,8,11),Qt.AlignmentFlag.AlignCenter,'1')
    p.end();return QIcon(pix)

def time_text(ms):
    n=max(0,int(ms))//1000
    return f'{n//60}:{n%60:02d}'

class MusicPlayerBar(QWidget):
    exit_requested=Signal()

    def __init__(self,music,parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.music=music;self.list_open=False;self._futures=[]
        self.setStyleSheet('''
          QWidget { font-family: "Microsoft YaHei UI"; font-size: 11px; }
          QLabel { color: #f3f4f6; background: transparent; }
          QPushButton { border: none; border-radius: 12px; background: transparent; }
          QPushButton:hover { background: rgba(255,255,255,24); }
          QPushButton#play { background: rgba(255,255,255,36); border-radius: 19px; }
          QPushButton#play:hover { background: rgba(255,255,255,58); }
          QPushButton:disabled { background: transparent; }
          QSlider::groove:horizontal { height: 3px; border-radius: 1px; background: rgba(255,255,255,45); }
          QSlider::sub-page:horizontal { background: #e1e5ec; border-radius: 1px; }
          QSlider::handle:horizontal { background: #e1e5ec; width: 8px; margin: -3px 0; border-radius: 4px; }
          QListWidget { border: none; background: transparent; color: #f3f4f6; outline: none; }
          QListWidget::item { padding: 6px 4px; border-radius: 5px; }
          QListWidget::item:selected { background: rgba(255,255,255,32); color: #ffffff; }
          QScrollBar:vertical { background: transparent; width: 4px; }
          QScrollBar::handle:vertical { background: rgba(255,255,255,90); border-radius: 2px; min-height: 16px; }
          QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height: 0; }
        ''')
        self.title=QLabel(self);self.title.setStyleSheet('font-size:13px;font-weight:600;')
        self.subtitle=QLabel(self);self.subtitle.setStyleSheet('color:#bdc3cd;font-size:10px;')
        self.progress=QSlider(Qt.Orientation.Horizontal,self)
        self.progress.sliderReleased.connect(lambda:music.seek(self.progress.value()))
        self.elapsed=QLabel(self);self.duration=QLabel(self)
        for label in (self.elapsed,self.duration):label.setStyleSheet('color:#bdc3cd;font-size:10px;')
        self.duration.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.buttons={}
        actions=[('close','返回聊天，音乐继续播放',self.exit_requested.emit),('mode','播放模式',self.show_modes),
                 ('previous','上一首',lambda:self.command('previous')),('play','播放 / 暂停',self.toggle_play),
                 ('next','下一首',lambda:self.command('next')),('list','选择歌曲',self.toggle_list),('back','返回播放',self.toggle_list)]
        for key,tip,callback in actions:
            b=QPushButton(self);b.setObjectName(key);b.setIcon(icon(key));b.setIconSize(QSize(20,20));b.setToolTip(tip)
            b.clicked.connect(callback);self.buttons[key]=b
        self.track_list=QListWidget(self);self.track_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.track_list.itemClicked.connect(self.choose_track)
        music.changed.connect(self.sync);music.tracks_changed.connect(self.rebuild_list)
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(100)
        music.refresh();self.rebuild_list();self.arrange();self.sync()

    def resizeEvent(self,event):self.arrange();self.sync()

    def arrange(self):
        w,h=self.width(),self.height()
        self.buttons['close'].setGeometry(w-34,7,26,26);self.buttons['back'].setGeometry(7,7,26,26)
        if self.list_open:
            self.title.setGeometry(40,8,w-80,24);self.track_list.setGeometry(12,35,w-24,h-44)
        else:
            self.title.setGeometry(16,11,w-58,23);self.subtitle.setGeometry(16,34,w-42,16)
            self.progress.setGeometry(16,53,w-32,12)
            self.elapsed.setGeometry(17,64,56,15);self.duration.setGeometry(w-74,64,56,15)
            y=max(80,h-50);center=w//2
            for key,x,size in [('mode',center-119,28),('previous',center-68,30),('play',center-19,38),('next',center+38,30),('list',center+91,28)]:
                self.buttons[key].setGeometry(x,y+(38-size)//2,size,size)
        self.track_list.setVisible(self.list_open);self.buttons['back'].setVisible(self.list_open)
        for child in [self.subtitle,self.progress,self.elapsed,self.duration]+[self.buttons[k] for k in ['mode','previous','play','next','list']]:child.setVisible(not self.list_open)

    def command(self,command,**args):
        future=Future();self._futures.append(future)
        self.music.dispatch({'command':command,**args},future,defer_for_reply=False)

    def poll(self):
        for f in list(self._futures):
            if f.done():
                self._futures.remove(f);result=f.result()
                if not result.get('ok'):self.subtitle.setText(result.get('error','播放失败'))

    def toggle_play(self):
        state=self.music.status()['status']
        self.command('pause' if state=='playing' else 'resume' if state=='paused' else 'play')

    def show_modes(self):
        menu=QMenu(self)
        for mode,label in MODES.items():
            action=menu.addAction(label);action.setCheckable(True);action.setChecked(self.music.playlist.mode==mode)
            action.triggered.connect(lambda checked=False,value=mode:self.command('set_mode',mode=value))
        menu.exec(self.buttons['mode'].mapToGlobal(self.buttons['mode'].rect().bottomLeft()))

    def toggle_list(self):
        self.list_open=not self.list_open;self.music.refresh();self.arrange();self.sync()

    def choose_track(self,item):
        self.command('play',path=item.data(Qt.ItemDataRole.UserRole));self.list_open=False;self.arrange();self.sync()

    def rebuild_list(self):
        self.track_list.clear()
        for path in self.music.playlist.tracks:
            item=QListWidgetItem(path.stem);item.setData(Qt.ItemDataRole.UserRole,str(path));item.setToolTip(path.name);self.track_list.addItem(item)
        self.sync()

    def sync(self):
        s=self.music.status()
        title=f'播放列表 · {s["track_count"]} 首' if self.list_open else Path(s['path']).stem if s['path'] else '选择一首歌'
        self.title.setText(self.title.fontMetrics().elidedText(title,Qt.TextElideMode.ElideMiddle,max(1,self.title.width())));self.title.setToolTip(title)
        states={'playing':'正在播放','paused':'已暂停','stopped':'本地曲库','loading':'加载中','queued_after_reply':'开场白后播放'}
        self.subtitle.setText(s['error'] or f'{states[s["status"]]}  ·  {MODES[s["mode"]]}')
        self.buttons['play'].setIcon(icon('pause' if s['status']=='playing' else 'play','#ffffff'))
        self.buttons['mode'].setIcon(icon(s['mode']));self.buttons['mode'].setToolTip(MODES[s['mode']]+' · 点击切换')
        for k in ['play','previous','next']:self.buttons[k].setEnabled(bool(self.music.playlist.tracks))
        if not self.progress.isSliderDown():self.progress.setRange(0,s['duration_ms']);self.progress.setValue(s['position_ms'])
        self.elapsed.setText(time_text(s['position_ms']));self.duration.setText(time_text(s['duration_ms']))
