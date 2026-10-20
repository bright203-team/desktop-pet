# AIによるデスクトップペットの導入

公開リポジトリのリンクを渡されて「これほしい」「入れて」と頼まれた Codex / Claude Code は、この手順で導入してください。これは利用者向けの配布物です。新しいアプリの開発・リポジトリの作成・開発用ハーネスの導入は不要です。Claude / ChatGPT アプリ本体には手を加えません。

## 1. 変更前に、1回のメッセージでまとめて確認

ファイルの作成、ダウンロード、設定変更、前提ソフトの導入を始める前に、次をまとめて聞いて返事を待ってください。既に分かる答えは埋めて確認し、同じことを再度聞かないでください。

> このアプリは Windows 10・11 専用です。使うPCはWindowsですか？ Windowsでなければ導入せず終了します。
>
> ChatGPT の Codex または Claude Code を使う人向けです。どちらを使っていますか？ どちらも使わなくても、Windowsにかわいいペットを表示するアプリとして使えますが、作業中・考え中・入力待ちなどの反応は動きません。それでも入れますか？ ペットを重ねて表示する Claude / ChatGPT のデスクトップアプリも必要です。
>
> Codexを使う場合、使っているプランは何ですか？ 無料プランでは利用枠が足りず、導入を最後まで進められない可能性があります（不可能と断定しません。枠はプラン・利用状況で変わります）。
>
> 連動させる先を選んでください：Claude Code・Codex Windows・Codex WSL・連動なし。Windowsログイン時の自動起動も有効にしますか？ 選んだ連動先のペット用hooksの追加・更新と、自動起動を選んだ場合の登録を行ってよいですか？ 既存の他のhooksは残します。
>
> 足りないもの（Python 3.14 と Python Launcher、Node.js 22 以上）をAIが自動で入れてよいですか？ 導入に必要なパッケージと配布元の利用条件を確認して同意して進めます。可能なものはユーザー単位で入れます。管理者の確認が出る場合だけ事前に伝えます。

Windows以外、または導入への同意がない場合は、何も変更せず終了します。プランの回答が不明なだけで導入を止めたり、枠の変更・有料契約を勝手に行ったりしないでください。

## 2. 返事のあとはAIが最後まで行う

利用者にコマンドの実行・ZIPの展開・設定ファイルの編集を頼まないでください。AI自身がコマンドを実行し、終了コードと結果を確認します。作業できるWindowsの端末を使います。WSL内のエージェントならWindows側のPowerShellを呼び、Windows側のユーザーと保存先で導入します。LinuxのPythonにWindowsアプリを入れてはいけません。

### OSと前提の確認・不足分の導入

- WindowsのOS情報を取得し、Windows 10・11であることを実際に確認します。`py -3.14 --version` と `node --version` でWindows側の前提を検査します。既存の別の版を削除しません。
- 許可された不足分だけを `winget` で導入します。まず `winget show --id Python.Python.3.14 --exact --source winget` と `winget show --id OpenJS.NodeJS.LTS --exact --source winget` で現在の提供内容・対応する導入範囲を確認してください。PythonにはLauncherの `py` が必要です。導入後に `py` がなければ `Python.Launcher` の提供内容を確認して追加します。
- ユーザー単位が可能なら、以下を不足しているものに限って実行します。Nodeの提供版が22以上であることも確認してください。

```powershell
winget install --id Python.Python.3.14 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
winget install --id OpenJS.NodeJS.LTS --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
```

- ユーザー単位に対応しないパッケージは、その理由と管理者の確認が出ることを事前に伝え、最初の許可の範囲で対応する導入範囲を使います。UACはAIで代行・回避できないため、OSが要求した承認だけは利用者に案内します。再起動の強制はしません。`winget` が使えない場合もAIが公式の導入方法を調べ、許可された範囲で準備します。
- PATHの更新はAIが新しいPowerShellプロセスかプロセス環境の再読込で行い、利用者に端末を開き直すよう頼みません。`py -3.14 --version` と `node --version` が条件を満たすまで確かめます。未許可の不足分がある場合は、導入できたと報告せず理由を示します。
- Codex WSLが選ばれた場合は、既定のWSLとそのNode.js 22以上も事前確認します。Windows側のwingetはWSL内のNodeを入れません。不足していれば、最初に得たNode導入の許可の範囲でそのディストリビューションの公式の方法を使ってAIが準備します。WSL自体や新しいディストリビューションを勝手に追加しません。

### Releaseを取得して展開

リポジトリをcloneする必要はありません。固定URLから配布ZIPを取得します。

https://github.com/bright203-team/desktop-pet/releases/latest/download/desktop-pet.zip

以下はWindows PowerShellで実行する例です。一意な一時フォルダを使い、既存の展開先を上書きしません。PowerShellのエラーと外部コマンドの非ゼロ終了は失敗として扱ってください。

```powershell
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$work = Join-Path ([IO.Path]::GetTempPath()) ('desktop-pet-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$zip = Join-Path $work 'desktop-pet.zip'
Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/bright203-team/desktop-pet/releases/latest/download/desktop-pet.zip' -OutFile $zip
Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $work 'expanded')
$bundles = @(Get-ChildItem -LiteralPath (Join-Path $work 'expanded') -Directory)
if ($bundles.Count -ne 1) { throw 'Expected one release folder' }
$installer = Join-Path $bundles[0].FullName 'scripts/install.ps1'
if (!(Test-Path -LiteralPath $installer -PathType Leaf)) { throw 'Missing installer' }
```

### 回答に合わせて質問なしで導入

`install.ps1` に必ず `-Yes` を付けます。全て選んだ場合の例：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $installer -Yes -CodexWindows -CodexWsl -Autostart
if ($LASTEXITCODE -ne 0) { throw 'Pet installation failed' }
```

回答とオプションの対応は次のとおりです。希望のない登録を追加しないでください。

| 回答 | 渡すオプション |
|---|---|
| Claude Codeと連動する | 既定で登録するので追加不要 |
| Claude Codeと連動しない | `-NoClaude` |
| Codex Windowsと連動する | `-CodexWindows` |
| Codex WSLと連動する | `-CodexWsl` |
| どのCodexとも連動しない | `-NoCodex` |
| 連動なしでペットだけ使う | `-NoClaude -NoCodex` |
| ログイン時に自動起動する | `-Autostart` |
| 新しく自動起動を登録しない | `-Autostart` を付けない |

`-Yes` により任意項目の質問を省きます。通常は導入後に起動するので `-NoStart` は付けません。更新の場合、以前の連動・自動起動の登録は省略オプションだけでは解除されません。既存の設定と登録を読み取り、残る登録があれば結果で伝えてください。他のhooksを消したり、利用者の既存設定を初期値で上書きしたりしません。

### 起動と登録をAIが検証

- 導入先は `Join-Path $env:USERPROFILE '.claude-desktop-pet/app'`。アプリ、同梱画像、仮想環境の `Scripts/pythonw.exe` があることを確認します。
- `Get-CimInstance Win32_Process` で、その導入先の `pythonw.exe` が `-m desktop_pet` を実行していることを確認します。起動コマンドの成功だけでは完了としません。既存プロセスや他のPythonを一括終了しないでください。
- 選んだ先の設定をAIが読み取り、ペット用hooksが導入先の `scripts/pet/state-hook.mjs`（Claude）または `scripts/pet/codex-hook.mjs`（Codex）を指すことと、既存の他のhooksが保持されたことを確認します。Claude Codeは `%USERPROFILE%/.claude/settings.json`、Codex Windowsは `%USERPROFILE%/.codex/hooks.json`、Codex WSLは既定のWSLの `~/.codex/hooks.json` です。設定の秘密の値は表示しません。
- 自動起動を選んだ場合は、Startupフォルダの `ClaudeDesktopPet.lnk` の実体と導入先への参照を確認します。
- 画面確認が使えるならペットと通知領域のアイコンを確認します。表示先のClaude / ChatGPTアプリが閉じている・最小化中なら表示されないため、プロセスの起動と画面表示の確認を区別します。画面が読めない場合は未確認と明記し、導入・起動・登録の自動検査を続けます。反応の確認は新しいセッションとhooksの信頼登録後になります。

## 3. 最後の報告は短く

導入・起動・選択した連動先・自動起動の結果と、未確認があればその内容を伝えます。利用者に残る操作は「Claude Code / Codex の新しいセッションを開く」「Codexで必要なら `/hooks` で内容を確認して信頼する」だけを短く案内してください。hooksの信頼を迂回するオプションは使いません。OSの管理者承認など避けられなかった操作がある場合は、その理由を説明します。

参考：[WinGetの導入オプション](https://learn.microsoft.com/en-us/windows/package-manager/winget/install)、[Codex hooksと信頼](https://developers.openai.com/codex/hooks)。プランによる上限は変わるため、無料プランでの導入可否は断定せず、現在の利用状況に応じて案内します。
