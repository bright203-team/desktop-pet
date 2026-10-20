"""Stable scene identifiers, compatibility rows and authoring defaults."""
SCENES = dict(zip(('idle_blink','idle_smug','idle_peek','idle_play','idle_sleep','hover','click','drag_right','drag_left','offline','waiting','working','done'),
                 ('まばたき','なまいき','のぞきこむ','遊びだす','寝る','片手を振る','♡ジャンプ','右へ小走り','左へ小走り','布団で寝る','指つんつん','PCカタカタ＋汗','ピース＋キラキラ')))
LEGACY = dict(zip(SCENES, ('idle','idle','idle','idle','idle','jumping','waving','running-right','running-left','failed','waiting','running','review')))
FALLBACKS = {scene: 'idle_blink' for scene in SCENES if scene != 'idle_blink'}
# Numbering follows the supplied preview.js, including the two drag sheets last.
IMPORT_SCENES = ('idle_blink','idle_smug','idle_peek','idle_play','idle_sleep','hover','click','offline','waiting','working','done','drag_right','drag_left')
DEFAULT_DURATIONS = dict(zip(IMPORT_SCENES, (
    (1600,180,90,150,600,900), (650,200,450,650,200,450),
    (500,200,350,1000,350,500), (500,250,350,600,350,500),
    (800,700,500,700,500,3000), (500,200,220,220,220,400),
    (200,180,220,180,180,700), (500,)*6, (500,250,200,300,200,600),
    (200,)*6, (400,300,300,450,450,450), (120,)*8, (120,)*8)))
