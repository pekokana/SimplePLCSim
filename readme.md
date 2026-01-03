# PLC / SCADA 学習用 簡易シミュレータ (PLC-SCADA Lab)

## 概要

本リポジトリは、Webエンジニアの視点で**PLC（Programmable Logic Controller）のスキャンモデルとSCADAとの通信挙動を理解するため**に開発した学習用シミュレータです。

物理的なPLC実機やセンサーがなくても、Python上で「制御ロジック（PLC）」「物理デバイス（装置）」「プロセス監視（Orchestrator）」を動かし、Modbus TCPを介したデータの流れを体感・検証できます。

## システム構成図

1. **Orchestrator**: プロセス管理。PLC、Device、IODeviceを依存関係に基づき起動・監視。
2. **PLC Simulator**: ロジック演算（ラダー実行） + Modbus TCP サーバー。
3. **Device Simulator**: 仮想デバイス。PLCに接続し、センサー信号（X）を送り、出力（Y）を模倣。
4. **IODevice (Bridge)**: 異なるPLC間、あるいはPLCと外部システムを繋ぐ「神経」。条件に応じたデータ転送やハートビート監視を担当。

## 特徴

* **PLCスキャンサイクルの再現**: 読み込み・演算・出力の1サイクルをループ実行。
* **堅牢な再接続ロジック**: 通信途絶時もCPU負荷を抑えながら自動復帰を試みる「スマート・リコネクト」機能を搭載。
* **マルチプロセス管理**: `orchestrator.py` による一括管理。依存関係に基づいた起動順序制御。
* **カオスエンジニアリング**: 意図的なプロセス停止（`chaos kill`）による、SCADA側のエラーハンドリング検証。



## セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/pekokana/SimplePLCSim
cd SimplePLCSim

# 仮想環境の作成と依存ライブラリのインストール
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

```

## 実行方法

最も簡単な方法は、オーケストレーターを使用して一括起動することです。

### 1. システム全体の一括起動（推奨）

```bash
python orchestrator.py orchestrator.yaml

```

これにより、PLC（`plcsim.py`）とデバイス（`devicesim.py`）が自動的に立ち上がり、相互に通信を開始します。

### 2. 個別起動（デバッグ用）

```bash
# PLCの起動
python plcsim.py plc_conf/plc_A/plc_A.yaml plc_conf/plc_A/ladder_A.yaml

# デバイスの起動
python devicesim.py device_conf/grinder.yaml

```

---
# 各機能の詳細について

- `doc\architecture.md` を参照してください。
---

## ラダーロジック構文ルール (Lark準拠)

本シミュレータのラダーロジックは、独自のLark構文定義（`ladder_parser.py`）に従って記述する必要があります。

### 基本構造

1行（1 Rung）は必ず **[条件式] --(出力命令)** の形式で記述します。

### 命令セットと記述例

| 命令カテゴリ | 命令名 | 構文定義上の構成 | YAMLでの記述例 |
| --- | --- | --- | --- |
| **コイル出力** | `(DEVICE)` | `DEVICE` | `X0 --(Y0)` |
| **タイマー** | `TON` / `TOF` | `INST DEVICE NUMBER` | `M0 --(TON T1 3000)` |
| **カウンタ** | `CTU` | `INST DEVICE NUMBER` | `X1 --(CTU C0 10)` |
| **リセット** | `RES` | `"RES" DEVICE` | `X2 --(RES C0)` |
| **代入・演算** | `=` | `calc_expr` | `M1 --(D10 = 100)` |

### 記述の鉄則（重要）

1. **接点始動**: 行の先頭は必ず接点（X, Y, M, T, C）または `[` で始めてください。
2. **出力の括弧**: 全ての出力命令（TON, RES, 演算等）は `--(` と `)` で囲む必要があります。
3. **出力の連結**: 1つの条件に対して、複数の出力を繋げることができます。
* 例: `X0 --(Y0) --(TON T1 500) --(D0 = 1)`


4. **タイマーの完了接点**: `TON T1` がタイムアップすると、接点 `T1` が自動的に True になります。


## Modbus アドレスマップ

外部 SCADA や HMI から接続する際の標準的なデータ配置です。本シミュレータでは、デバイスのサイズ拡張による干渉を防ぐため、固定オフセット方式を採用しています。

### 1. ビットデータ (Coils / Discrete Inputs)

| デバイス | アドレス範囲 | Modbus種別 (FC) | 役割 |
| --- | --- | --- | --- |
| **X** (入力) | `0` 〜 | Discrete Inputs (FC2) | 外部センサー、スイッチ等の入力状態 |
| **Y** (出力) | `0` 〜 | Coils (FC1/5/15) | モーター、ランプ等のアクチュエータ制御 |
| **M** (内部) | **`1000`** 〜 | Coils (FC1/5/15) | 制御ロジック用補助リレー |

> **Note**: Y と M は同じ Coil 領域に属しますが、M を 1000 番から配置することで、Y の点数が増えてもデータが重複しない設計になっています。

### 2. ワードデータ (Holding Registers)

| デバイス | アドレス範囲 | Modbus種別 (FC) | 役割 |
| --- | --- | --- | --- |
| **D** (データ) | `0` 〜 | Holding Regs (FC3/6/16) | 数値データ、タイマー/カウンタ現在値 |
| **System** | **`10000`** 〜 | Holding Regs (FC3) | PLCの状態監視・診断情報 |

#### システムレジスタ詳細 (`10000`〜)

* `+0`: **Heartbeat** (0.5秒おきに 0/1 が反転)
* `+1`: **Scan Count** (プログラムの実行回数)
* `+2`: **Uptime** (起動からの経過秒数)
* `+5`: **Chaos Latency** (ここに書き込んだ数値[秒]だけ Modbus 応答を遅延) 

## デバイスからのDiscrete Input (Device / IODevice)

### X領域（入力信号）への特殊書き込み「SIM_INJECT」
通常、Modbusの Discrete Inputs は読み取り専用であり、外部から書き込むことはできません。
しかし、本シミュレータではセンサー入力を模倣するため、以下の仕組みを導入しています。

- プロキシ・インジェクション:
  - Device や IODevice が type: discrete を指定して write_coil 命令を発行した際、書き込み先が X領域 (0-99) であれば、サーバー内部で本来書き換え不可能な DI用物理メモリを強制的に更新 します。

- メリット:
  - 通信プロトコルの作法を守った監視（Read）を行いつつ、シミュレータからの外部操作（Write）による「物理現象の注入」が可能です。

### IODevice(Bridge)の拡張
仮想デバイスからのDiscrete Inputsへ模擬対応したことで、IODeviceシミュレータを活用した複数PLC連携に活用が行えます。

- 複数工程連携:
  - PLC_A の出力（Y0）をトリガーに、PLC_B の入力（X0）へ信号を転送するなどのインターロックを YAML 定義のみで実現。

- 通信種別の自動判別:
  - type: discrete 指定により、Modbusの制約を回避した X領域への信号注入（SIM_INJECT）をサポート。


## インタラクティブ管理コンソール (CLI)

`orchestrator.py` を起動すると、各プロセスの標準出力は自動的にログファイルへリダイレクトされ、画面上には専用のプロンプトが表示されます。

### 主要コマンド

| コマンド | 内容 | 実行例 |
| --- | --- | --- |
| **`status`** (or `ls`) | 全プロセスの稼働状況、PID、Ready状態を一覧表示 | `status` |
| **`addr`** | 対象とするPLCのmodbusアドレスマッピング情報を表示 | `addr plc1` |
| **`info`** | 対象とするPLCの実行中のメモリ情報を表示 | `info plc1` |
| **`log`** | ログディレクトリからファイルを選択し、末尾数行を表示 | `log` |
| **`chaos`** | 意図的な障害（停止・遅延）を注入する | `chaos kill plc1` |
| **`help`** | 利用可能なコマンド一覧を表示 | `help` |
| **`exit`** | 全サービスを安全に停止して終了 | `exit` |


## カオスエンジニアリング（障害注入テスト）

SCADAのアラーム検知や再接続ロジックをテストするために、以下の障害を意図的に発生させることができます。

### 1. プロセスの強制終了・停止

* **`chaos kill <name>`**: プロセスを強制終了させます。PLCの場合、Orchestratorが検知して自動再起動を試みます（自動復旧テスト）。
* **`chaos stop <name>`**: プロセスを停止し、自動再起動を無効化します（メンテナンスや長期ダウンのテスト）。
* **`chaos resume <name>`**: 停止させたプロセスを再起動します。

### 2. 通信遅延（ネットワーク揺らぎ）の注入 

* **`chaos delay <name> <sec>`**:
指定した秒数だけModbusの応答を遅延させます。プロセスは生存しているが応答が極端に遅い「高負荷」や「通信不良」の状態を再現し、SCADA側のタイムアウト挙動を確認できます。

### 3. パケットロスの注入  <実装中>

* **`chaos ploss on/off <name> `**:
現在実装中ですが、たまに応答しないようなパケットロス挙動を設定可能になります。




## ライセンス

MIT License

