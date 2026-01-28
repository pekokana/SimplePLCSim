# ビルドガイド (Executable Creation Guide)

本プロジェクトの各コンポーネントを Python スクリプトからWindows用の実行可能ファイル (.exe) にビルドする手順について説明します。

## 1. 開発環境の準備

本プロジェクトはパッケージ管理に [uv](https://github.com/astral-sh/uv) を使用しています。

### 1.1 pyinstallerの追加について

* 配布物へ含める必要がないため、開発用途として追加します。

```bash
uv add --dev pyinstaller
```

## 2. ビルドコマンド

`uv run` を使用して、プロジェクトの仮想環境にインストールされた PyInstaller でビルドを行います。

### 2.1 Orchestrator (管理ツール)

プロセス監視 (`psutil`) と通信 (`pymodbus`) の依存関係をすべて含めてビルドします。

```bash
uv run pyinstaller --onefile --clean orchestrator.py
```

**ビルド後動作確認で異常が生じた場合**

以下のコマンドでexeの再作成をして、改めて動作確認を行う。

```bash
uv run pyinstaller --onefile --clean --collect-all pymodbus --collect-all psutil orchestrator.py
```

### 2.2 PLC Simulator (PLC本体)

PLCロジックの解析とModbusサーバー機能を含めてビルドします。

```bash
uv run pyinstaller --onefile --clean plcsim.py
```

**ビルド後動作確認で異常が生じた場合**

以下のコマンドでexeの再作成をして、改めて動作確認を行う。

```bash
uv run pyinstaller --onefile --clean --collect-all pymodbus plcsim.py
```

### 2.3 Device Simulator (デバイス側)

```bash
uv run pyinstaller --onefile --clean devicesim.py
```

**ビルド後動作確認で異常が生じた場合**

以下のコマンドでexeの再作成をして、改めて動作確認を行う。

```bash
uv run pyinstaller --onefile --clean --collect-all pymodbus devicesim.py
```

### 2.4 IO Device Simulator (入出力デバイス側)

```bash
uv run pyinstaller --onefile --clean iodevicesim.py
```

**ビルド後動作確認で異常が生じた場合**

以下のコマンドでexeの再作成をして、改めて動作確認を行う。

```bash
uv run pyinstaller --onefile --clean --collect-all pymodbus iodevicesim.py
```

## 3. 配布パッケージの構成

ビルド完了後、`dist/` フォルダ内に生成された `.exe` ファイルを以下の構成で配置して使用してください。

```text
dist/
├── orchestrator.exe
├── plcsim.exe
├── devicesim.exe
├── iodevicesim
├── orchestrator.yaml   (必須: 各種設定)
├── *.yaml              (必須: PLC定義、ラダー定義ファイル)
└── logs/               (実行時に自動生成)

```

## 4. 注意事項

* **パス解決**: プログラム内部で `sys._MEIPASS` を使用して、エグゼ化後のリソースパスを動的に解決しています。
* **管理者権限**: `psutil` による他プロセスの監視や `kill` 操作を行う際、Windows の実行環境によっては管理者権限が必要になる場合があります。
* **Hidden Imports**: ライブラリのアップデート等により実行時に `ModuleNotFoundError` が発生した場合は、`--collect-all` または `--hidden-import` オプションの追加を検討してください。

## 99. Appendix

## 動作確認用yaml例

* WindowsのD:ドライブで動作確認をする場合を想定

### orchestrator.yaml

```yaml
kind: orchestrator
version: "1.0"
log:
  dir: "D:/dev/SimplePLCSim/dist/logs"
services:
  # ---燃料タンク01 ---
  - name: plc_fuel1
    type: plc
    command: ["D:/dev/SimplePLCSim/dist/plcsim.exe"]
    args: 
      - "D:/dev/SimplePLCSim/dist/plc_fuel1.yaml"
      - "D:/dev/SimplePLCSim/dist/ladder_fuel1.yaml"
    ready_check:
      kind: modbus
      host: 127.0.0.1
      port: 15001

  # ---燃料送信デバイス01
  - name: dev_fuel1
    type: device
    command: ["D:/dev/SimplePLCSim/dist/devicesim.exe"]
    args: ["D:/dev/SimplePLCSim/dist/device_fuel1.yaml"]
    depends_on: [plc_fuel1]
```

### plc_fuel1.yaml

```yaml
kind: plc
version: "1.0"
name: "plc_fuel1"
log_dir: "D:/dev/SimplePLCSim/dist/logs"
power: true
cpu:
  scan_cycle_ms: 100
memory:
  X: 100
  Y: 100
  M: 100
  D: 100
modbus:
  port: 15001
```

### ladder_fuel1.yaml

```yaml
kind: ladder
version: "1.0"
rungs:
  # 1. 常時ON（TRUE）を利用して D0 を毎スキャンカウントアップ
  - "[ X0 ] --(D0 = D0 + 1)"
  # 2. D0が1000を超えたら 0 にリセット（これで数値が 0~1000 をループします）
  - "[ D0 > 100 ] --(D0 = 0)"
  # 3. D0が500以上のときだけ M10 をONにする（ON/OFFの確認用）
  - "[ D0 > 50 ] --(M10)"
  # 4. システムの生存確認用（10000番のHeartbeatとは別に、D1をスキャンごとに+1）
  - "D1 --(D1 = D1 + 1)"
  - "END"
```

### device_fuel1.yaml

```yaml
kind: device
version: "1.0"
device:
  name: "fuel_unit_1"
  log_dir: "D:/dev/SimplePLCSim/dist/logs"
  plc:
    host: localhost
    port: 15001
    heartbeat_offset: 512
  cycle_ms: 100
  signals:
    upstream_ready:
      type: discrete
      address: 0
      pattern:
        - { value: true, duration_ms: 5000 }
        - { value: false, duration_ms: 5000 }
```
