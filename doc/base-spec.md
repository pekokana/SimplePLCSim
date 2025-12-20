これは
・PLCシミュレータ
・Modbus/TCP対応
・複数PLC起動
・SCADA開発用

を **すべて満たす構成** を目指したいです。



# まず全体像（完成形）

```
plc-simulator/
├─ README.md
├─ requirements.txt
├─ run_plc.py              ← PLC起動エントリポイント
│
├─ core/                   ← PLCの本体ロジック
│  ├─ __init__.py
│  ├─ plc.py               ← PLC全体（電源・CPU）
│  ├─ cpu.py               ← スキャン制御
│  ├─ memory.py            ← X/Y/M/D メモリ
│  ├─ ladder_engine.py     ← ラダー実行エンジン
│  ├─ io_module.py         ← I/Oモジュール定義
│  └─ power.py             ← 電源ON/OFF
│
├─ comm/                   ← 通信系
│  ├─ __init__.py
│  ├─ modbus_server.py     ← Modbus/TCPサーバ
│  └─ address_map.py       ← Modbus ↔ PLC メモリ対応
│
├─ config/                 ← 外部定義（PLCごと）
│  ├─ plc01/
│  │  ├─ plc.yaml          ← 電源・CPU・I/O構成
│  │  ├─ io_map.yaml       ← I/O割付・タグ
│  │  ├─ ladder.yaml       ← ラダー定義
│  │  └─ modbus.yaml       ← Modbusアドレス定義
│  │
│  └─ plc02/
│     ├─ plc.yaml
│     ├─ io_map.yaml
│     ├─ ladder.yaml
│     └─ modbus.yaml
│
├─ utils/
│  ├─ __init__.py
│  ├─ yaml_loader.py       ← YAML読み込み
│  ├─ logger.py            ← ログ
│  └─ timer.py             ← スキャン周期管理
│
└─ tests/
   ├─ test_ladder.py
   ├─ test_memory.py
   └─ test_modbus.py
```



# 各ディレクトリの「役割」と「設計思想」

## 🔹 run_plc.py（超重要）

```text
・PLCを1台起動するだけのスクリプト
・引数で plc01 / plc02 を指定
```

**複数起動が簡単になる**



## 🔹 core/（PLCそのもの）

### plc.py

* 電源
* CPU
* I/O
* メモリ
* 通信をまとめる「器」

**PLC筐体に相当**



### cpu.py

* スキャンループ
* ラダー実行タイミング制御




### memory.py

* X / Y / M / D 配列
* 排他制御（将来）

**PLC内部デバイス**



### ladder_engine.py

* ladder.yaml を解釈
* 論理演算実行

**最重要モジュール**



### io_module.py

* 入力16点
* 出力16点
* モジュール単位で管理




### power.py

* 電源ON/OFF
* OFF時はスキャン停止

**PLCらしさ**



## 🔹 comm/（通信）

### modbus_server.py

* Modbus/TCPサーバ
* SCADAからの要求受付



### address_map.py

* Coil 100 → Y0
* Holding 0 → D0

**PLCとSCADAの橋渡し**



## 🔹 config/（PLCの設計書）


### plc.yaml（構成）

```yaml
power: true

cpu:
  scan_cycle_ms: 100

io:
  input_modules:
    - name: QX40
      points: 16
  output_modules:
    - name: QY40
      points: 16

memory:
  M: 256
  D: 256
```



### io_map.yaml（I/O割付）

```yaml
X0: START_SW
X1: STOP_SW
Y0: MOTOR_RUN
Y1: RUN_LAMP
```



### ladder.yaml（制御）

```yaml
- rung:
    logic: "X0 OR M0"
    coil: "M0"

- rung:
    logic: "M0 AND NOT X1"
    coil: "Y0"
```



### modbus.yaml（通信）

```yaml
coil:
  0: X0
  1: X1
  100: Y0
  200: M0

holding:
  0: D0
```



## 🔹 utils/（共通）

* YAML読み込み
* ログ
* タイマー

**後でSCADAログ解析にも使える**



## 🔹 tests/（品質担保）

* ラダー評価
* メモリ更新
* Modbus応答

**実務で強い**



# この構成の「強さ」

・PLC台数を増やせる
・SCADAを本気で作れる
・実機PLCの概念と完全一致

