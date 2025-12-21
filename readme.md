# PLC / SCADA 学習用 簡易シミュレータ

## 概要

本リポジトリは、
**SCADAおよびPLCの理解を目的とした学習用シミュレータ** です。

PLC実機が手元にない環境でも、

* PLCのスキャンモデル
* メモリ構造（X / Y / M / D）
* ModbusによるI/O
* センサー値の揺らぎ

を体験できることを目的としています。


## 特徴

* PLCスキャン方式を再現
* X / Y / M / D メモリモデル
* YAMLによる設定駆動
* Modbus TCP通信
* センサーの変動・パルス信号再現

※ 実機PLCの完全再現を目的としたものではありません。



## 動作環境

* Python 3.10 以上
* OS: Windows / Linux / macOS

### 使用ライブラリ

* pymodbus
* PyYAML



## セットアップ

```bash
pip install -r requirements.txt
```



## 実行方法

### PLCシミュレータ起動

```bash
python run_plc.py plc.yaml ladder.yaml
```

### デバイスシミュレータ起動

```bash
python device_simulator.py device_conf/sample_device.yaml
```



## 学習目的について

本プロジェクトは、

* PLCとは何か
* SCADAがPLCから「何を」「どう取得しているか」
* データが不安定であることを前提とした設計

を理解するための **学習・検証用ツール** です。



## 今後の拡張予定

* 状態遷移のイベント化
* メッセージング連携
* SCADA的タグ管理
* 履歴データの蓄積



## ライセンス

MIT License



## 最後に

Webエンジニア視点でSCADA・PLCを理解しようとした試行錯誤の成果です。
同じような興味を持つ方の参考になれば幸いです。
