"""Character authoring rules independent of Qt and Win32."""
from dataclasses import dataclass
from pathlib import Path
import os
import re

ANIMATIONS = (
    ('idle', '通常（何もしていないとき）', '呼吸・まばたき', 6),
    ('running-right', '右移動（右へドラッグ中）', '右向きに小走り', 8),
    ('running-left', '左移動（左へドラッグ中）', '左向きに小走り', 8),
    ('waving', 'あいさつ（触ったとき・作業完了時）', '手を振る', 4),
    ('jumping', 'ジャンプ（マウスを乗せたとき）', 'しゃがむ→跳ぶ→着地', 5),
    ('failed', '失敗（エラー発生時）', '驚く→落ち込む→立ち直る', 8),
    ('waiting', '返事待ち（返事・許可待ち）', '「まだ？」と見上げる', 6),
    ('running', '作業中（AIが作業・思考中）', '手を動かす・考え込む', 6),
    ('review', '確認して（結果を見てほしいとき）', '「できたよ」と得意げに見せる', 6),
    ('gaze', '視線（マウスの方向を見るとき）', '顔と目線を16方向に向ける', 16),
)


def characters_root(home=None):
    return Path(os.environ.get('CLAUDE_PET_CHARACTERS_PATH') or
                Path(home or os.environ.get('USERPROFILE') or Path.home()) / '.claude-desktop-pet' / 'characters')


def incoming_root():
    return Path(os.environ.get('CLAUDE_PET_INCOMING_PATH') or
                Path(os.environ.get('USERPROFILE') or Path.home()) / '.claude-desktop-pet' / 'incoming')


APPROVED_PROMPT = Path(__file__).with_name('character_prompt.txt').read_text(encoding='utf-8')


@dataclass
class CharacterFlow:
    name: str = ''
    step: str = 'identity'

    def identity(self, name):
        name = name.strip()
        reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{i}' for prefix in ('COM', 'LPT') for i in range(1, 10)}
        if (not name or name in ('.', '..') or
                any(c in '<>:"/\\|?*' or ord(c) < 32 for c in name) or
                name.endswith('.') or name.split('.')[0].upper() in reserved):
            raise ValueError('名前にはフォルダに使える文字を入力してください。記号や予約名は使えません。')
        self.name = name
        self.step = 'prompt'

    @property
    def destination(self):
        return incoming_root() / self.name

    def back(self):
        self.step = 'identity'

    def cancel(self):
        self.step = 'cancelled'

    def prompt(self):
        return APPROVED_PROMPT


@dataclass
class ImportPlan:
    version: int
    sheet: Path | None
    rows: list
    expressions: dict


def validate_image(path, size, image_size):
    actual = image_size(path)
    if actual != size:
        raise ValueError(f'{path.name}：必要な大きさ {size[0]}×{size[1]}、実際 {actual}。')


def sheet_plan(sheet, expressions, image_size):
    sheet = Path(sheet)
    size = image_size(sheet)
    if size not in ((1536, 1872), (1536, 2288)):
        raise ValueError(f'{sheet.name}：v1は1536×1872、v2は1536×2288が必要です（実際 {size}）。')
    expressions = {key: Path(value) for key, value in expressions.items() if value}
    for key, path in expressions.items():
        if key not in ('idle_smile', 'idle_angry'): raise ValueError('未知の表情差分です。')
        validate_image(path, (1536, 208), image_size)
    return ImportPlan(1 if size[1] == 1872 else 2, sheet, [], expressions)


def folder_plan(folder, image_size):
    groups = {}
    for item in Path(folder).iterdir():
        if item.is_dir() and re.match(r'^[0-9]{2}_', item.name):
            number = int(item.name[:2])
            if number not in range(1, 14) or number in groups:
                raise ValueError(f'{item.name}：段番号が重複しているか範囲外です。')
            groups[number] = item
    missing = set(range(1, 12)) - groups.keys()
    if missing: raise ValueError(f'段フォルダが不足しています：{sorted(missing)}')
    rows, expressions, gaze_angles = [], {}, []
    for number, group in sorted(groups.items()):
        files = [p for p in group.iterdir() if p.suffix.lower() == '.png' and p.is_file()]
        expected = ANIMATIONS[number-1][3] if number <= 9 else (8 if number <= 11 else 6)
        if len(files) != expected:
            raise ValueError(f'{group.name}：必要 {expected}コマ、実際 {len(files)}コマです。')
        def order(path):
            if number in (10, 11):
                match = re.search(r'([0-9]+(?:[_.][0-9]+)?)度', path.stem)
                if not match: raise ValueError(f'{path.name}：視線の角度がありません。')
                return float(match[1].replace('_', '.'))
            matches = re.findall(r'[0-9]+', path.stem)
            if not matches: raise ValueError(f'{path.name}：コマ番号がありません。')
            return int(matches[-1])
        files.sort(key=order)
        values = [order(p) for p in files]
        if len(set(values)) != len(values): raise ValueError(f'{group.name}：番号・角度が重複しています。')
        if number in (10, 11): gaze_angles.extend(values)
        for path in files: validate_image(path, (192, 208), image_size)
        if number <= 11: rows.append(files)
        else: expressions['idle_smile' if number == 12 else 'idle_angry'] = files
    if gaze_angles != [i*22.5 for i in range(16)]:
        raise ValueError('視線の10・11段は0度から337.5度まで22.5度刻みで8枚ずつ必要です。')
    return ImportPlan(2, None, rows, expressions)
