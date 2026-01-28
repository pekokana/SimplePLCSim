## Internal Components & Behavior Reference

## 0. 読み方ガイド

### このドキュメントの目的

本ドキュメントは、SimplePLCSim を構成する各コンポーネントの**内部構造と動作モデル**を、
実装者・検証者向けに整理した設計仕様書です。

* [Architecture.md](doc/Architecture.md) : 全体思想・責務分離・構成意図
* **Components.md : 各コンポーネントが内部で何をしているか**

をそれぞれ明確に分離しています。

### 本ドキュメントで扱うこと / 扱わないこと

**扱うこと**

* 処理フロー（スキャン・ループ・監視）
* 設定ファイルの構造と意味
* コンポーネント単位の責務

**扱わないこと**

* Pythonコードの逐次解説
* 実装クラス図
* Modbusアドレス完全一覧（→ [Modbusメモリ](doc/ModbusMemoryMap.md)）


## 1. コンポーネント一覧

| コンポーネント            | 役割             |
| ------------------ | -------------- |
| PLC Simulator      | 制御ロジック実行・メモリ管理 |
| Device Simulator   | 物理入力・センサー挙動生成  |
| IODevice Simulator | PLC間連携・イベント演算  |
| Orchestrator       | プロセス管理・障害注入    |

---

## 2. PLC Simulator

### 2.1 役割と責務

* ラダーロジックの実行
* 内部メモリ（X/Y/M/D/SYS）の管理
* Modbus TCP サーバー提供

### 2.2 内部処理モデル（スキャンサイクル）

PLC は `scan_cycle_ms` ごとに以下の処理を繰り返します。

1. **入力同期**

   * Discrete Input（X）を内部メモリへ反映
2. **ロジック評価**

   * `ladder.yaml` を Lark パーサーで解析
   * 上から順に逐次実行
3. **タイマー／カウンタ更新**
4. **出力同期**

   * Y / M / D / SYS を Modbus データストアへ反映

この処理モデルは、**実PLCの Scan Model を意図的に模倣**しています。

### 2.3 設定ファイル仕様（plc.yaml）

PLC の演算周期・メモリ規模・公開ポートを定義します。

```yaml
kind: plc              # 固定値
version: "1.0"         # 固定値
name: "plc_conv"       # PLCの名称
log_dir: logs          # ログファイルの出力先
power: true            # 固定値（電源ONを意味します）
cpu:
  scan_cycle_ms: 100   # スキャン周期（小さいほど高速・高負荷）
memory:
  X: 100               # 入力点数 (設定上限：100)
  Y: 100               # 出力点数 (設定上限：100)
  M: 100              # 内部リレー (設定上限：100)
  D: 100              # データレジスタ (設定上限：100)
modbus:
  port: 15030          # 外部（Device/SCADA）**が接続するポート**
```



## 3. Device Simulator

### 3.1 役割

* PLC への入力信号（X / D）の生成
* 時間変化を持つ物理挙動の模倣

### 3.2 device.yaml 構造

```yaml
kind: device
version: "1.0"

device:
  name: dev_press        # デバイス識別名
  log_dir: logs          # ログ保存先
  plc:
    host: localhost      # 接続先PLCのホスト
    port: 15021          # 接続先PLCのModbusポート
    heartbeat_offset: 512# 接続先PLCへのハートビートアドレスオフセット(ここは固定値としてください)
  cycle_ms: 100          # 更新間隔（シミュレーションの分解能）

  signals:
    # ビット信号のシミュレーション
    power:
      type: discrete         # X (Discrete Input) を操作
      address: 0         # 書き込み先アドレス (X0)
      pattern:
        - value: true
          duration_ms: 500
        - value: false
          duration_ms: 10000

    # 数値データのシミュレーション
    motor_rpm:
      type: register     # D (Holding Register) を操作
      address: 0         # 書き込み先アドレス (D0)
      pattern:
        - value: 0
          duration_ms: 100
        - value: 100
          duration_ms: 300
```

### 3.3 信号タイプ

* **discrete** : X領域（外部入力）操作
* **coil** : Y / M 強制操作（デバッグ用途）
* **register** : D領域（アナログ値）
* **pulse** : 単発ON（coilで代替可能）

### 3.4 動作モデル

* 起動時に PLC へ Modbus TCP 接続
* `cycle_ms` ごとに信号状態を更新
* `duration_ms` 経過時に値を書き換え



## 4. IODevice Simulator

### 4.1 役割

* PLC間の信号ブリッジ
* イベント駆動型演算
* 生存監視（ハートビート）

### 4.2 iodevice.yaml 構造

```yaml
kind: iodevice
version: "1.0"
name: "bridge_logic"      # サービス識別名
heartbeat_offset: 512　　　# 接続先PLCへのハートビートアドレスオフセット(ここは固定値としてください)
cycle_ms: 200             # 転送・監視の周期
log_dir: "logs"           # ログ保存先

connections:
  # 例1: ビット信号の転送（PLC1のY0 -> PLC2のX10）
  - name: "transfer_signal"
    trigger: {host: "localhost", port: 15020, address: 0, type: "coil"} 
    target:  {host: "localhost", port: 15030, address: 10, type: "discrete"}

  # 例2: 数値演算アクション（トリガーONでDレジスタを加算）
  - name: "count_up_logic"
    trigger: {host: "localhost", port: 15020, address: 1, type: "coil"}
    actions:
      - {host: "localhost", port: 15020, address: 100, type: "hr", op: "increment", value: 1}
```

### 4.3 ブリッジ動作

* trigger の立ち上がり／立ち下がりを検出
* target へ同状態を書き込み

### 4.4 イベント駆動アクション

* OFF→ON の瞬間のみ演算実行
* set / increment / decrement をサポート

### 4.5 ハートビート監視

* SYS領域アドレスを周期監視
* 5秒以上無変化の場合、対象PLC停止と判断
* 自身も FATAL 停止



## 5. Orchestrator

### 5.1 役割

* プロセス起動・停止管理
* 依存関係解決
* Chaos（障害）注入

### 5.2 orchestrator.yaml 構造

```yaml
kind: orchestrator
version: "1.0"
log:
  dir: "logs"

services:
  # --- 制御層 (PLC) ---
  - name: plc_press
    type: plc           # 制御ロジックを実行。異常終了時は自動再起動
    command: [plcsim.py]
    args: ["path/to/plc.yaml", "path/to/ladder.yaml"]
    ready_check:
      kind: modbus
      host: 127.0.0.1
      port: 15020

  # --- 神経層 (IODevice) ---
  - name: bridge_logic
    type: iodevice      # PLC間のデータ転送やイベント演算を担当
    command: [iodevicesim.py]
    args: ["path/to/bridge.yaml"]
    depends_on: [plc_press, plc_conv] # 接続先PLCが立ち上がってから起動

  # --- 物理層 (Device) ---
  - name: press_sensor
    type: device        # センサーやスイッチなどの物理的な時間変化を模倣
    command: [devicesim.py]
    args: ["path/to/device.yaml"]
    depends_on: [plc_press]
```

### 5.3 サービスタイプ別動作

| type     | 役割  | 特性        |
| -------- | --- | --------- |
| plc      | 制御核 | 自動再起動     |
| iodevice | 連携  | Ready待ち起動 |
| device   | 物理  | 時間挙動生成    |

### 5.4 起動シーケンス

1. PLC 起動
2. Ready チェック
3. IODevice / Device 起動

### 5.5 CLI と内部動作

* Orchestrator 自身が Modbus Client
* PLC プロセスを汚さず内部状態参照
