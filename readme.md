# PLC / SCADA Learning Simulator (SimplePLCSim)

SimplePLCSim は、**PLC・通信・SCADA が「壊れたとき」の挙動を学ぶための**
Python 製 PLC / SCADA シミュレータです。

物理 PLC や実機ネットワークがなくても、  
産業システム特有の「中途半端な異常状態」を再現できます。


## 何ができる？

- PLC の **スキャンサイクル**（Read → Execute → Write）を再現
- **Modbus TCP** による実通信
- PLC / Device / IO を **マルチプロセス**で分離起動
- 通信遅延・CPU フリーズ・プロセス断などの **Chaos 制御**
- SCADA の **監視・再接続・復旧ロジック**検証


## こんな人向け

- PLC / SCADA を **ソフトウェア視点で理解したい**
- 実機なしで **障害試験・PoC・学習**をしたい
- SCADA の **Heartbeat / Timeout / Ready 判定**を検証したい

## 向いていない人

- 実 PLC の完全互換を求める人
- 制御理論や IEC 規格の学習が目的の人



## 最短で動かす

```bash
git clone https://github.com/pekokana/SimplePLCSim
cd SimplePLCSim

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

python orchestrator.py orchestrator.yaml

# pyproject.tomlも付属しているため、uvでの実行も可能です
# uvを利用する際には特に設定は必要ありません。
````

---

## ドキュメント構成

* **まず読む**

  * **[Readme](readme.md)

* **詳しい仕様・設計**

  * **[全体構成](doc/Architecture.md) : 全体構成・プロセス関係
  * **[コンポーネント](doc/Components.md) : Orchestrator / PLC / Device 詳細
  * **[CLI操作](doc/CLI.md) : Orchestrator CLI 操作
  * **[Chaos設計](doc/ChaosDesign.md) : Chaos制御の思想と仕様と状態遷移
  * **[Modbusメモリ](doc/ModbusMemoryMap.md) : メモリモデル・アドレスマップ
  * **[ラダー構文](doc/LadderSyntax.md) : ラダー構文・命令セット


## ライセンス

MIT License

