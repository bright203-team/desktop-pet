# 導入の手引き

## 準備

Windows 10・11 に次のものを入れ、PowerShell を開き直します。

1. [Python 3.14](https://www.python.org/downloads/windows/)（Python Launcher もインストール）。`py -3.14 --version` が Python 3.14 を表示することを確認します。
2. [Node.js 22 以上](https://nodejs.org/)。`node --version` で確認します。

ZIP を書き込み可能な場所に展開します。PowerShell で、展開した `desktop-pet-<版>` フォルダを開いてください。展開場所やユーザー名の固定はありません。起動後のデータの保存先は `%USERPROFILE%/.claude-desktop-pet/` です。

## 導入

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/install.ps1
```

Claude Code の hooks を登録します。Codex Windows・Codex WSL・ログイン時の自動起動について順番に質問します。必要なものに `y`、不要なら Enter を押します。WSL を選ぶ場合は、既定の WSL ディストリビューションに Node.js 22 以上が必要です。

質問なしで Claude Code・Windows Codex・自動起動を有効にする例：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/install.ps1 -Yes -CodexWindows -Autostart
```

`-CodexWsl` で WSL の Codex も登録できます。`-NoCodex` は Codex の新しい登録を省きます。`-Yes` だけなら任意項目を追加しません。以前の登録は維持します。`-NoStart` は導入後の起動を省きます。

導入先は `%USERPROFILE%/.claude-desktop-pet/app/` です。両方のキャラ・絵・Python の環境・起動スクリプトをここに置きます。開発用のハーネスは不要です。導入はこのユーザーの Claude Code の設定を編集し、選択した場合は Codex の設定と自動起動も登録します。他の hooks は残します。

導入後は Claude Code・Codex のセッションを開き直してください。Codex は必要に応じて `/hooks` で確認して信頼します。通知領域のアイコンから「設定…」で連動先やキャラの大きさを選べます。

## 起動と更新

通常は導入の最後に起動します。手動で起動する場合：

```powershell
$app = Join-Path $env:USERPROFILE '.claude-desktop-pet/app'
& (Join-Path $app 'scripts/start.ps1')
```

更新時は通知領域の「終了」で閉じ、新しい ZIP を別の場所に展開して同じ導入コマンドを実行してください。設定・位置・追加キャラは保持します。自動更新はありません。更新後は展開元の ZIP フォルダを移動しても導入版を起動できます。

## キャラの追加

「設定…」→「キャラを追加」で、画像作成用のプロンプトを作り、別の画像生成ツールで作った絵を取り込みます。スプライトシートは v1（1536×1872）・v2（1536×2288）。個別 PNG は画面の説明に従って親フォルダを選びます。元画像は変更しません。追加したキャラは `%USERPROFILE%/.claude-desktop-pet/characters/` に保存します。

## 削除

通知領域の「終了」で閉じてから実行します。

```powershell
$app = Join-Path $env:USERPROFILE '.claude-desktop-pet/app'
& (Join-Path $app 'scripts/uninstall.ps1')
```

このペットの hooks・自動起動・アプリを削除し、他の hooks は残します。設定と位置を消すか質問します。Enter で保持します。質問なしなら `-Yes`、設定と位置も消すなら `-Yes -RemoveSettings` を付けます。追加キャラは残るので、不要なら保存先から削除してください。WSL に登録した場合は削除時にも同じ WSL を使える状態にします。

## 困ったとき

- Python・Node が無い、または版が違うと、日本語の案内で導入が止まります。上の動作環境を入れて PowerShell を開き直します。
- 起動しないときは導入先の `scripts/setup.ps1`、次に `scripts/start.ps1` を実行します。Claude / ChatGPT が最小化されていないかも確認してください。
- hooks の設定 JSON が壊れている場合は、元ファイルを書き換えずに止まります。控えを取って JSON を直してから再実行します。
- 更新・削除でファイル使用中のエラーが出たら、通知領域からペットを終了して再実行します。ほかの Python プロセスは終了しないでください。
- 連動しない場合は新しいセッションと Codex の hooks の信頼を確認します。通常のチャット画面の応答は連動の対象外です。
