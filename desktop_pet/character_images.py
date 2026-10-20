"""Qt image adapter and staged, lossless character storage."""
import json
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from PySide6.QtGui import QImage, QPainter
from .character import ANIMATIONS, characters_root, folder_plan, sheet_plan


def read_image(path):
    image = QImage(str(path))
    if image.isNull(): raise ValueError(f'{Path(path).name}：画像を読み込めません。')
    return image


def image_size(path):
    image = read_image(path)
    return image.width(), image.height()


def populated(image):
    # Work on raw alpha bytes rather than calling pixelColor millions of times.
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return any(bytes(rgba.constBits())[3::4])


def validate_strip(image, count, label, row=0):
    for column in range(8):
        present = populated(image.copy(column*192, row*208, 192, 208))
        if present != (column < count):
            raise ValueError(f'{label}：{column+1}コマ目は' + ('画像が必要です。' if column < count else '透明にしてください。'))


def assemble(files, height=208):
    image = QImage(1536, height, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        for row, paths in enumerate(files):
            for column, path in enumerate(paths):
                frame = read_image(path)
                if image_size(path) != (192, 208) or not populated(frame):
                    raise ValueError(f'{path.name}：192×208の空白ではない画像が必要です。')
                painter.drawImage(column*192, row*208, frame)
    finally:
        painter.end()
    return image


def import_character(name, source, expressions=None, individual=False, root=None):
    """Validate everything before making the character discoverable; never touch source."""
    if not name.strip(): raise ValueError('キャラの名前を入力してください。')
    if individual and any(p.is_file() and re.match(r'^\d{2}_.*\.png$', p.name, re.I) for p in Path(source).iterdir()):
        return import_scenes(name, source, root)
    plan = (folder_plan(source, image_size) if individual else
            sheet_plan(source, expressions or {}, image_size))
    sheet = assemble(plan.rows, 2288) if individual else read_image(plan.sheet)
    for row, animation in enumerate(ANIMATIONS[:9]):
        validate_strip(sheet, animation[3], animation[0], row)
    if plan.version == 2:
        for row in (9, 10): validate_strip(sheet, 8, f'視線 {row+1}段目', row)
    extras = {}
    for key, value in plan.expressions.items():
        image = assemble([value]) if individual else read_image(value)
        validate_strip(image, 6, key)
        extras[key] = image
    root = Path(root) if root is not None else characters_root()
    root.mkdir(parents=True, exist_ok=True)
    character_id = uuid4().hex
    destination = root / character_id
    with TemporaryDirectory(prefix='.import-', dir=root) as temporary:
        stage = Path(temporary) / character_id
        stage.mkdir()
        # QImage quality=100 selects lossless WebP encoding.
        if not sheet.save(str(stage/'spritesheet.webp'), 'WEBP', 100):
            raise OSError('キャラの画像を保存できません。')
        for key, image in extras.items():
            if not image.save(str(stage/f'{key}.png'), 'PNG'):
                raise OSError('表情差分を保存できません。')
        (stage/'pet.json').write_text(json.dumps(dict(id=character_id, displayName=name.strip(),
            spriteVersionNumber=plan.version, spritesheetPath='spritesheet.webp'), ensure_ascii=False), encoding='utf-8')
        stage.rename(destination)
    return destination


def inspect_scenes(source, numbered=False, stored=False):
    """Validate without creating directories or modifying input."""
    from .scenes import SCENES, IMPORT_SCENES, DEFAULT_DURATIONS
    source = Path(source)
    if not source.is_dir():
        raise ValueError('置き場所のフォルダがありません。')
    files = {}
    for path in source.iterdir():
        if stored and path.name in ('pet.json', 'scenes.json'):
            continue
        if numbered and path.name in ('main.png', 'character.txt'):
            if not path.is_file():
                raise ValueError(f'{path.name}：ファイルが必要です。')
            if path.name == 'main.png':
                if path.read_bytes()[:8] != bytes((137,80,78,71,13,10,26,10)):
                    raise ValueError('main.png：PNG形式の画像が必要です。')
                read_image(path)
            continue
        if numbered:
            match = re.match(r'^(\d{2})(?:_|\.|$)', path.name)
            if not match or int(match[1]) not in range(1, 14):
                raise ValueError(f'{path.name}：01.png〜13.pngの番号付きPNGが必要です。')
            number = int(match[1])
            if number in files:
                raise ValueError(f'{number:02d}：番号が重複しています。')
            if not path.is_file() or path.suffix.lower() != '.png' or path.read_bytes()[:8] != bytes((137,80,78,71,13,10,26,10)):
                raise ValueError(f'{path.name}：PNG形式の画像が必要です。')
            files[number] = path
            continue
        if path.is_file() and path.suffix.lower() == '.png':
            match = re.match(r'^(\d{2})_', path.name)
            if not match or int(match[1]) not in range(1,14):
                raise ValueError(f'{path.name}：01_〜13_のPNGが必要です。')
            number = int(match[1])
            if number in files: raise ValueError(f'{number:02d}：番号が重複しています。')
            files[number] = path
    if not set(range(1,13)).issubset(files):
        missing = '、'.join(f'{i:02d}.png' for i in sorted(set(range(1,13))-files.keys()))
        raise ValueError('01〜12のPNGが必要です（13枚目は任意）。不足：' + missing)
    # The reference predates the approved numerical order. Recognize only its
    # complete, explicit labels; generic names always use the approved order.
    sample_labels = ('まばたき','なまいき','のぞきこむ','遊びだす','寝る','マウスオーバー','クリック','接続不可','返事許可待ち','作業中','作業完了','ドラッグ中_右','ドラッグ中_左')
    sample = all(label in files[i+1].stem for i,label in enumerate(sample_labels) if i+1 in files)
    order = IMPORT_SCENES if sample or numbered else tuple(SCENES)
    if not (sample or numbered) and 13 not in files:
        raise ValueError('01_〜13_のPNGが必要です。不足：[13]')
    entries = {}
    for number, scene in enumerate(order,1):
        path = files.get(number, files[12])
        columns, rows = (4 if number >= 12 else 3), 2
        width, height = image_size(path)
        if width < columns or height < rows or abs(width/columns-height/rows) > 1:
            raise ValueError(f'{path.name}：{columns}列×2段のほぼ正方形のコマが必要です（実際 {width}×{height}）。')
        count = columns*rows
        times = DEFAULT_DURATIONS[scene]
        if len(times) != count:
            # Preserve total duration when the approved grid has a different
            # count from the older reference; no invented dropped frames.
            total = sum(times)
            times = [round(total/count)]*count
            times[-1] += total-sum(times)
        entries[scene] = dict(file=path.name, columns=columns, rows=rows,
                              frames=count, durations=list(times))
    right = entries['drag_right']
    left = entries['drag_left']
    if ((sample or numbered) and 13 not in files) or (
            read_image(source/left['file']).convertToFormat(QImage.Format.Format_RGBA8888) ==
            read_image(source/right['file']).convertToFormat(QImage.Format.Format_RGBA8888)):
        entries['drag_left'] = dict(right, durations=list(right['durations']), mirror=True)
    return entries, files


def import_scenes(name, source, root=None, numbered=False):
    """Validate first, then copy atomically; never touch incoming files."""
    if not name.strip():
        raise ValueError('キャラの名前を入力してください。')
    entries, files = inspect_scenes(source, numbered)
    root = Path(root) if root is not None else characters_root()
    root.mkdir(parents=True, exist_ok=True)
    character_id = uuid4().hex
    destination = root / character_id
    with TemporaryDirectory(prefix='.import-', dir=root) as temporary:
        stage = Path(temporary) / character_id
        stage.mkdir()
        for path in files.values(): shutil.copyfile(path, stage/path.name)
        if numbered:
            for filename in ('main.png', 'character.txt'):
                path = Path(source)/filename
                if path.is_file():
                    shutil.copyfile(path, stage/filename)
        (stage/'scenes.json').write_text(json.dumps(entries, ensure_ascii=False), encoding='utf-8')
        (stage/'pet.json').write_text(json.dumps(dict(id=character_id, displayName=name.strip(), sceneFormatVersion=1), ensure_ascii=False), encoding='utf-8')
        stage.rename(destination)
    return destination


def source_sha(source, stored=False):
    """Fingerprint every approved input, including optional-file absence."""
    import hashlib
    source = Path(source)
    _, files = inspect_scenes(source, numbered=True, stored=stored)
    digest = hashlib.sha256()
    paths = [files.get(i) for i in range(1,14)] + [source/'main.png', source/'character.txt']
    for index, path in enumerate(paths):
        digest.update(str(index).encode() + b'\0')
        if path is not None and path.is_file():
            digest.update(path.name.encode() + b'\0')
            data = path.read_bytes()
            digest.update(str(len(data)).encode() + b':' + data)
        else:
            digest.update(b'absent')
    return digest.hexdigest()
