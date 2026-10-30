# comfyui-gtx1080-nix

NixOS 上の NVIDIA GeForce GTX 1080 向け ComfyUI 環境です。
`yDog-1/nix-config` から切り出した構成で、対応対象は Linux x86_64 と GTX 1080 です。
ほかの Pascal GPU や GPU 世代での動作は保証しません。

Home Manager が起動コマンドと Nix の Python 3.12 を提供し、`uv` がレビュー済みの
ハッシュ付き `requirements.lock` に従って、書き込み可能な専用環境へ依存関係を導入します。
CUDA と cuDNN は nixpkgs ではなく、固定した PyTorch wheel の依存関係から導入します。
初期の cu126 構成は[公式の環境定義](https://github.com/Comfy-Org/ComfyUI-Standalone-Environments/blob/main/requirements-nvidia-cu126.txt)に合わせています。
cuDNN 9.10.2 の指定は意図的です。9.11 以降では Pascal 対応が削除されています。
Manager のパッケージ検査に必要な `torchaudio` も `requirements-extra.txt` で明示し、
`constraints.txt` に従って PyTorch と同じ cu126 系のバージョンを lock に含めます。

## 導入と起動

### Home Manager への組み込み

以下の GitHub URL は、このリポジトリを公開した後に使用できます。
利用側の flake に input を追加し、Home Manager の `modules` にモジュールを追加します。

```nix
inputs.comfyui-gtx1080-nix = {
  url = "github:yDog-1/comfyui-gtx1080-nix";
  inputs.nixpkgs.follows = "nixpkgs";
};

# home-manager.lib.homeManagerConfiguration の引数
modules = [
  inputs.comfyui-gtx1080-nix.homeModules.default
  # 既存の Home Manager モジュール
];
```

Home Manager モジュールは起動コマンドの導入だけを行い、activation 時の通信や
venv 作成は行いません。単独でコマンドをビルドする場合は `nix build` を使います。
既存の `nix-config` から切り替えても、データの保存先とコマンド名は変わりません。
旧 `comfyui.nix` の import は、新モジュールへの切り替え時に取り除いてください。

### 実行

Home Manager の設定を適用してから、以下を実行します。

```sh
comfyui-setup
comfyui
```

ブラウザーで <http://127.0.0.1:8188> を開きます。モデル、入力、出力、ワークフロー、
カスタムノードは `${XDG_DATA_HOME:-$HOME/.local/share}/ComfyUI` 以下に保存します。
待受アドレスは `0.0.0.0` です。他の端末からは `http://<このマシンのIPアドレス>:8188` で接続します。
ファイアウォールは自動では開放しません。認証を設定せずに、インターネットへ直接公開しないでください。
セットアップではモデルをダウンロードしません。候補環境を有効化する前に、CUDA 演算、
cuDNN を明示的に使う畳み込み演算、Manager を含む ComfyUI の起動を検証します。
画像生成には、別途入手したチェックポイントとワークフローが必要です。

ComfyUI-Manager は標準で有効です。`custom_nodes` への手動 clone や追加の pip install は不要です。
本体の `manager_requirements.txt` もハッシュ付き lock に含め、セットアップ・修復時に導入します。
Manager の依存に含まれる PyPI 版 `uv` は NixOS で実行できないため、venv 内の
`uv` / `uvx` は GC ルートで保持した Nix 版へのリンクに置き換えます。
起動時には `VIRTUAL_ENV` と `UV_PYTHON` を指定し、Manager のパッケージ操作も
現在の専用環境へ向けます。本体は Nix で固定したソースを各環境の `app/` へコピーし、
書き込み可能な状態で実行します。拡張が本体の `web/extensions` などへ書き込んでも、
読み取り専用の Nix store には影響しません。
本体の更新は Manager ではなく、下記の依存関係の更新手順を使います。
既存環境から移行する場合は Home Manager を適用してから `comfyui-setup` を再実行してください。

### カスタムノードの依存を追加する

Manager で拡張を追加した後や、更新・修復で venv を作り直した後には、ComfyUI を停止して
以下を実行できます。拡張を追加するたびに Nix 設定や本体用 lock を変更する必要はありません。

```sh
comfyui-install-deps --dry-run
comfyui-install-deps
comfyui-check
comfyui
```

`custom_nodes/` 直下の各拡張の `requirements.txt` を収集し、現在の venv に
`uv pip install` でまとめて導入します。シンボリックリンクの拡張も対象ですが、
隠しディレクトリと名前が `.disabled` で終わる拡張は除外します。
入れ子の拡張検索、`pyproject.toml`、独自の `install.py`、OS ライブラリの導入は対象外です。
requirements ファイルや Python パッケージのビルド処理も信頼できるものだけを使用してください。

- `--dry-run` は venv を変更せず解決結果を表示します。通信やキャッシュ更新は発生し得ます。
- すべての requirements を一度に解決し、GPU 関連の `constraints.txt` と cu126 を適用します。
  競合がある場合はエラーにし、制約を自動的に緩めません。
- `pip sync` ではないため無関係なパッケージは削除しませんが、解決に必要な依存の
  バージョンは変更される場合があります。本体用 lock の全パッケージを固定するものではありません。
- セットアップ・修復・このコマンドの同時実行はロックで防ぎます。ただし ComfyUI の起動や
  Manager のパッケージ操作はロックしないため、実行中はそれらを避けてください。
- 現在の venv を直接変更します。トランザクションや失敗時の自動ロールバックはありません。
  導入後は ComfyUI を再起動してください。問題があれば `comfyui-repair` で基礎環境を作り直せます。

Attention や VRAM 関連の回避策は強制しません。必要な場合だけフラグを指定します。

```sh
comfyui --lowvram
comfyui --disable-dynamic-vram
comfyui-check
```

DynamicVRAM が有効な間、`--lowvram` は効果がありません。
上流では回避用の `--disable-dynamic-vram` も非推奨になっているため、
常に必要な設定として依存しないようにしてください。

## 安全なセットアップと修復

- 通常のセットアップでは、実行環境 ID が一致する場合、現在の環境を再利用します。
- 本体が Nix store へのリンクになっている旧環境は、ID が一致していても新しい環境へ移行します。
- `comfyui-repair` は新しい環境を作成して検証します。既存の環境は削除しません。
- ロックによりセットアップと修復の同時実行を防ぎます。有効化時には `current` を
  アトミックに置き換え、それまで使用していた管理対象の環境を `previous` に記録します。
- 失敗した場合は `current` を変更せず、調査用に候補環境を残します。
- 従来の `app`、`.venv`、`constraints.txt`、`requirements.lock` は置き換えません。
  新方式での最初のセットアップが成功するまでは、起動コマンドから従来の環境も使用できます。
- 各候補環境の `environments/<id>/runtime` には、間接的な Nix GC ルートを作成します。
  これにより、Home Manager の更新や Nix GC の後も、その環境に必要なソースと Python を保持します。
  古い候補環境は自動では削除しません。
- 本体コピーへの変更は再利用時には保持しますが、更新・修復時には固定ソースから作り直します。
  拡張が本体配下へ独自に保存したデータは自動移行しません。永続データは共有の
  `models/`、`custom_nodes/`、`user/` などへ保存してください。

前の管理対象環境へ戻す場合は、ComfyUI を停止してから以下を実行します。

```sh
data="${XDG_DATA_HOME:-$HOME/.local/share}/ComfyUI"
(
  flock -n 9 || exit 1
  test -f "$data/previous/ready" || exit 1
  ln -s "$(readlink -f "$data/previous")" "$data/.rollback.$$"
  mv -Tf "$data/.rollback.$$" "$data/current"
) 9>"$data/.setup.lock"
```

戻るのは**実行環境だけ**です。共有データ、Manager が変更した `custom_nodes/`、
データベースの移行は元に戻りません。Manager による venv の依存変更も本体用 lock で
完全に固定されるわけではありません。拡張の更新前には `custom_nodes/` もバックアップしてください。
ComfyUI の更新前に `user/` をバックアップしてください。不要な環境を削除する場合は、
`current` と `previous` のどちらからも参照されていないことを先に確認してください。
環境のディレクトリを削除すると、その GC ルートも削除されます。
実行中の環境は削除しないでください。

## 依存関係の更新

### flake.lock の自動更新

GitHub Actions の `Update flake.lock` が毎週月曜日 09:00（日本時間）に
`nix flake update` を実行します。Actions 画面から手動実行もできます。
`nix flake check` が成功すると、変更がある場合に更新 PR を作成し、
既存の更新 PR があれば同じブランチを更新します。

リポジトリの Settings → Actions → General → Workflow permissions で
`Allow GitHub Actions to create and approve pull requests` を有効にしてください。
標準の `GITHUB_TOKEN` を使うため、生成された PR では別の CI ワークフローは
自動起動しません。更新ワークフロー内で検証結果を確認できます。

### ComfyUI の更新

1. 上流リリースのコミットと Nix ソースハッシュを確認して `comfyui/source.nix` を更新します。
   GPU 関連の依存構成を意図的に変更する場合は、`comfyui/constraints.txt` も更新します。
2. 新しい起動コマンドをビルドし、その中の `comfyui-update-lock` を使います。

   ```sh
   nix build
   ./result/bin/comfyui-update-lock comfyui/requirements.lock
   ```

3. lock ファイルの差分をレビューしてコミットします。通常のセットアップでは、
   `--require-hashes --strict --only-binary :all:` を指定して固定済みの依存関係を同期するだけで、
   依存関係の解決は行いません。
4. 新しい lock で Home Manager を再ビルドし、まず隔離したデータディレクトリで
   セットアップを実行します。本番データへ切り替える前に、SD 1.5 で実際に画像を生成して確認します。

初期の lock は Python 3.12、Linux x86_64 manylinux 2.28 向けに、
`2026-10-28T00:00:00Z` より前に公開されたパッケージを対象として解決しています。
明示的な更新コマンドでは、意図的に新しい依存関係も許可します。
カスタムノードのインストーラーにも主要な GPU 関連パッケージのバージョン制約を適用しますが、
カスタムノード自体は本体用の lock に含めません。

## テスト

```sh
python3 comfyui/test_setup.py -v
nix build --no-link .#checks.x86_64-linux.comfyui-setup
nix flake check --print-build-logs
nix fmt -- --fail-on-change
```

環境の作成・切り替えに関するテストには模擬インストーラーを使うため、
ネットワーク接続も GPU も不要です。実 GPU の検証は、別途 `comfyui-check` で行います。

`nix flake check` は以下をまとめて検証します。

- 起動コマンドのビルドと、生成したシェルスクリプトの ShellCheck
- 環境のセットアップ・切り替えに関するテスト
- Nix: Alejandra による整形、deadnix・statix による lint
- Python: Ruff による整形と lint
- Shell: shfmt による整形
- Markdown・YAML・JSON: Prettier による整形
- GitHub Actions: actionlint（`run` 内の ShellCheck を含む）
- クレデンシャル: Gitleaks（検出値はログで伏せ、検出時はチェック失敗）

`nix fmt` で上記フォーマッタをまとめて実行できます。
Python の大きな依存パッケージやモデルはセットアップ時に取得し、CI では取得しません。

Gitleaks の検査対象は flake に含まれる現在のソースで、Git 履歴や未追跡ファイルは含みません。
検査時にはソースが Nix store に入るため、秘密情報を置いてからチェックする運用は避けてください。
Nix store に入る前に確認する場合は、別途インストールした Gitleaks で
`gitleaks dir . --redact=100 --no-banner` を実行できます。
検査はすべての秘密情報の検出を保証するものではありません。
