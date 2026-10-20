import sys
import os
# Native rectangles and Qt widget coordinates must use the same physical pixels.
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
from PySide6.QtWidgets import QApplication
from .model import ROOT, data_root
from .app import InstanceLock
from .settings import PetManager

def main():
    if sys.platform != 'win32':
        return 0
    from .win32 import Win32
    app=QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    lock=InstanceLock(data_root(ROOT)/'runtime'/'pet.lock')
    (data_root(ROOT)/'runtime').mkdir(exist_ok=True)
    if not lock.acquire():
        return 0
    try:
        pet=PetManager(Win32)
        return app.exec()
    finally:
        lock.release()

if __name__=='__main__':
    raise SystemExit(main())
