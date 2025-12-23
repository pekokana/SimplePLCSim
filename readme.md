# PLC / SCADA 学習用 簡易シミュレータ (PLC-SCADA Lab)

## 概要

本リポジトリは、Webエンジニアの視点で**PLC（Programmable Logic Controller）のスキャンモデルとSCADAとの通信挙動を理解するため**に開発した学習用シミュレータです。

物理的なPLC実機やセンサーがなくても、Python上で「制御ロジック（PLC）」「物理デバイス（装置）」「プロセス監視（Orchestrator）」を動かし、Modbus TCPを介したデータの流れを体感・検証できます。

## 特徴

* **PLCスキャンサイクルの完全再現**: 読み込み・演算・出力の1サイクルをループ実行。
* **実戦的なラダー命令**:
* 接点（X, Y, M）の論理演算。
* タイマー命令（TON, TOF）、カウンタ命令（CTU）をサポート。


* **マルチプロセス・オーケストレーション**: `orchestrator.py` により、PLCとデバイスを独立したプロセスとして管理。依存関係に基づいた起動や死活監視、自動再起動が可能。
* **Modbus TCP ブリッジ**: PLC内部メモリ（X, Y, M, D）をModbus経由で外部公開。SCADA（別システム）からのポーリングを想定した設計。
* **デバイスエミュレーション**: センサーのゆらぎや、モーターの回転数変化、パルス信号などをYAML定義でシミュレート。

## システム構成図

1. **Orchestrator**: プロセス管理（PLCとDeviceを叩き起こし、監視する）
2. **PLC Simulator**: ロジック演算 + Modbus サーバー
3. **Device Simulator**: 仮想デバイス（Modbus クライアントとしてPLCに信号を送る）

## セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/pekokana/SimplePLCSim
cd SimplePLCSim

# 依存ライブラリのインストール
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

## ラダーロジック（命令セット）

`ladder.yaml` では以下の命令を記述可能です。

| 命令 | 内容 | 記述例 |
| --- | --- | --- |
| **Logic** | 論理演算（AND/OR/NOT） | `[X0 AND NOT X1] --(M0)` |
| **TON** | オンディレイタイマー | `TON T0 M0 2000 Y0` (M0がONで2秒後にY0がON) |
| **TOF** | オフディレイタイマー | `TOF T1 X1 3000 Y1` (X1がOFFで3秒後にY1がOFF) |
| **CTU** | カウントアップ | `CTU C0 X2 5 M1` (X2が5回ONしたらM1がON) |
| **RES** | リセット（カウンタ等） | `RES C0` |

## Modbus アドレスマップ

外部SCADA等から接続する場合の標準的なマッピングです。

* **Coils (0x)**: `0`〜 (X), `20`〜 (Y), `40`〜 (M)
* **Holding Registers (4x)**: `0`〜 (D), `10000`〜 (System Info: Heartbeat, Uptime)

## 今後の展望

* [ ] **SCADAダッシュボードの実装**: StreamlitやReactを用いたリアルタイム可視化。
* [ ] **履歴データ (Historian)**: InfluxDB等への時系列データ保存。
* [ ] **タグ管理メタデータ**: Modbusアドレスを論理名で管理する抽象化層の導入。

## ライセンス

MIT License

