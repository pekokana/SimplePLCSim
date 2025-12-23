作成していただいた `architecture.md` の原案は非常に整理されていますね！
アップロードされた最新のソースコード（特に `orchestrator.py` によるプロセス管理や `modbus_server.py` でのシステムレジスタ実装など）を反映し、**「より実践的なシステム構成図」**と**「詳細なアドレスマップ」**を加えた決定版を作成しました。



# PLC / SCADA 学習用シミュレータ 技術資料 (Technical Reference)

本資料は、本リポジトリのシステム構造および、YAML設定ファイルの記述仕様を解説したドキュメントです。

## 1. システム全体構成

本システムは、疎結合な3つのコンポーネントで構成され、**Orchestrator** がそれらを一括管理します。

* **Orchestrator (`orchestrator.py`)**:
* 各プロセスの起動順序（`depends_on`）の制御。
* Modbusポートの導通確認によるヘルスチェック。
* 異常終了時の自動再起動。


* **PLC Simulator (`plcsim.py`)**:
* ロジック演算の核。内部に Modbus サーバーを内蔵し、外部からのI/Oを受け付けます。


* **Device Simulator (`devicesim.py`)**:
* 物理デバイス（モーター、センサー等）を模倣し、Modbus クライアントとして PLC へ信号（X）を送り、PLC からの指令（Y/D）を受け取ります。





## 2. PLC 仕様詳細

### 2.1 メモリモデルと Modbus アドレスマップ

PLC内部メモリは以下のように Modbus アドレスにマッピングされています。SCADA開発時はこのアドレスを参照してタグ定義を行います。

| 種類 | 記号 | Modbus 種別 | アドレス範囲 | 説明 |
|  |  |  |  |  |
| **外部入力** | **X** | Coil | `0` ~ | センサー、スイッチ等（Deviceが書込） |
| **外部出力** | **Y** | Coil | `20` ~ | アクチュエータ、ランプ等（PLCが書込） |
| **内部リレー** | **M** | Coil | `40` ~ | 内部的なフラグ状態保持 |
| **データレジスタ** | **D** | Holding Reg | `0` ~ | 数値データ（16bit整数） |
| **システム情報** | **SYS** | Holding Reg | `10000` ~ | ハートビート、稼働時間、スキャン回数 |

> **Note:** システム情報は `modbus_server.py` 内の `HR_SYS_BASE` で定義されており、外部（SCADAやOrchestrator）から PLC の生存確認を行うために使用されます。

### 2.2 スキャンサイクル

1スキャン（`scan_cycle_ms` ごとに実行）の流れ：

1. **入力同期**: Modbus 経由で書き込まれた X アドレスの値を内部メモリへ反映。
2. **ロジック評価**: `ladder.yaml` に記述された命令を上から順に一行ずつ実行。
3. **タイマー・カウンタ更新**: 経過時間を計算し、T/C デバイスを更新。
4. **出力同期**: 演算結果（Y, M, D, SYS）を Modbus データストアへ反映。



## 3. 設定ファイル（YAML）仕様

### 3.1 PLC 設定 (`plc.yaml`)

CPUの性能やメモリサイズ、待ち受けポートを定義します。

```yaml
cpu:
  scan_cycle_ms: 100  # スキャン周期（小さいほど高速・高負荷）
memory:
  X: 8                # 入力点数
  Y: 8                # 出力点数
  M: 16               # 内部リレー点数
  D: 16               # データレジスタ数
modbus:
  port: 15020         # 待ち受けポート

```

### 3.2 ラダー命令 (`ladder.yaml`)

Pythonの式評価を利用した柔軟な記述が可能です。

* **論理演算**: `[入力条件] --(出力先)`
* 例: `"[X0 AND NOT X1] --(M0)"`


* **タイマー (TON/TOF)**: `{命令} {ID} {トリガ} {設定ms} {出力}`
* 例: `"TON T0 M0 2000 Y0"` （M0がONして2秒後にY0がON）


* **カウンタ (CTU)**: `CTU {ID} {カウント入力} {プリセット} {出力}`
* 例: `"CTU C0 X2 5 M1"` （X2が5回立ち上がったらM1がON）


* **リセット (RES)**: `RES {T/C ID}`
* 例: `"RES C0"`



### 3.3 デバイス設定 (`device.yaml`)

物理挙動をシミュレートするための「動き」を定義します。

```yaml
signals:
  power_btn:
    type: pulse       # 瞬間的に ON -> OFF する信号
    address: 2        # X2 へ送信
    pulse_ms: 500
  cycle_sensor:
    type: coil        # 継続的な変化
    address: 0        # X0 へ送信
    pattern:
      - { value: true, duration_ms: 2000 }
      - { value: false, duration_ms: 3000 }

```



## 4. Orchestrator によるプロセス管理

`orchestrator.yaml` では、システム全体の依存関係を定義します。

* **ready_check**: Modbus ポートが Listen 状態になるまで次のプロセスの起動を待機します。
* **依存関係**: `depends_on: [plc1]` と記述することで、PLCが起動完了してからデバイスを起動させる、といった制御が可能です。
* **死活監視**: PLC プロセスがクラッシュした場合、Orchestrator が検知して自動的に再起動を試みます。


このコンポーネントは、複数のプロセス（PLCやデバイス）を協調して動かす「システムの司令塔」の役割を担います。

### 4.1 Orchestrator の役割

Orchestrator は、複数の独立したシミュレータプロセスを管理します。

* **依存関係の解決**: PLC が起動して Modbus ポートが開いたことを確認してから、Device を起動させる。
* **一括起動・停止**: 1つのコマンドでシステム全体を立ち上げ、Ctrl+C で安全に全プロセスを終了させる。
* **プロセスの死活監視**: PLC 等のプロセスがクラッシュした際の検知と自動再起動。

### 4.2 orchestrator.yaml の構成

```yaml
kind: orchestrator
version: "1.0"

log:
  dir: logs          # 各プロセスの標準出力を保存するディレクトリ

services:
  - name: plc1
    type: plc
    command: [plcsim.py]
    args:
      - "plc_conf/plc_A/plc_A.yaml"
      - "plc_conf/plc_A/ladder_A.yaml"
    ready_check:      # 起動完了を判断する条件
      kind: modbus
      host: 127.0.0.1
      port: 15020
      timeout_sec: 15

  - name: device1
    type: device
    depends_on: [plc1] # plc1 が ready になるまで起動を待機
    command: [devicesim.py]
    args:
      - "device_conf/grinder.yaml"

```

### 4.3 サービス設定パラメータ

| パラメータ | 説明 |
|  |  |
| `name` | サービスを識別する一意の名前 |
| `type` | `plc` または `device`。`plc` の場合は異常終了時に自動再起動を試みます |
| `command` | 実行する Python スクリプト名 |
| `args` | スクリプトに渡す引数（設定ファイルのパス等） |
| `depends_on` | 起動前に準備完了（Ready）であるべきサービスのリスト |
| `ready_check` | サービスが正常に立ち上がったかを判定する設定 |

### 4.4 Ready Check (Modbus) の仕様

現在は `modbus` タイプに対応しています。

* 指定された `host` と `port` に対して Modbus TCP 接続を試行します。
* 接続に成功すれば「Ready」とみなし、依存する次のサービスの起動へ移ります。
* `timeout_sec` 以内に疎通できない場合は、起動失敗としてプロセスを停止します。

### 4.5 プロセス監視とリカバリ

* **監視サイクル**: 1秒ごとに全プロセスの生存を確認します。
* **自動再起動**: `type: plc` と定義されたサービスが終了した場合、Orchestrator は即座にその PLC を再起動し、再度 Ready 状態になるまで監視を継続します。
* **連鎖停止**: PLC がダウンした際、それに依存しているデバイスプロセスも一旦停止（または連鎖的な影響）を受ける挙動をシミュレートし、システム全体の一貫性を保ちます。


## 5. 学習のための Tips

本シミュレータを使って以下の挙動を確認してみてください。

1. **スキャンの遅延**: `scan_cycle_ms` を 1000（1秒）などに大きくすると、ボタン（X）を押してからランプ（Y）がつくまでのレスポンスが目に見えて遅れる「スキャンタイム」の影響を体感できます。
2. **パルス信号の取りこぼし**: デバイス側のパルス幅（`pulse_ms`）を PLC のスキャン周期より短く設定すると、PLC が信号を検知できない現象を確認できます。
3. **レースコンディション**: 同じ Y アドレスに対して、ラダーの上下で異なる条件を記述した場合、下の行の結果が優先される PLC 特有の挙動を観察できます。

