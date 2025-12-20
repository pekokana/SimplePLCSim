# ゴール（今日ここまで）

* Python製PLCシミュレータ
* **Modbus/TCP サーバとして起動**
* SCADA / Modbusクライアントから

  * Coil
  * Discrete Input
  * Holding Register
    を読める
* **PLC内部メモリ（X/Y/M/D）とModbusが対応**

---

# ① メモリ対応ルール（重要）

まず **割り切った対応表** を決めます（実機PLCでも同じ発想）。

| PLCメモリ | Modbus種別       | アドレス例  |
| ------ | -------------- | ------ |
| X      | Discrete Input | 10001〜 |
| Y      | Coil           | 00001〜 |
| M      | Coil           | 01001〜 |
| D      | Holding Reg    | 40001〜 |

👉 **ModbusはPLCの“窓口”**
👉 PLC内部のX/Y/M/Dをどう見せるかは「実装者の自由」

---

# ② 追加するファイル構成

```
plc-simulator/
├─ run_plc.py        ← PLC本体（修正）
├─ modbus_server.py  ← ★追加
├─ plc.yaml
└─ ladder.yaml
```

---

# ③ Modbusサーバ（modbus_server.py）

まず **即動く Modbus/TCP サーバ** を作ります。

```python
from pymodbus.server.sync import StartTcpServer
from pymodbus.datastore import (
    ModbusSlaveContext,
    ModbusServerContext,
    ModbusSequentialDataBlock
)
import threading

class ModbusBridge:
    def __init__(self, plc):
        self.plc = plc

        self.store = ModbusSlaveContext(
            di=ModbusSequentialDataBlock(0, [0]*100),  # X
            co=ModbusSequentialDataBlock(0, [0]*100),  # Y + M
            hr=ModbusSequentialDataBlock(0, [0]*100),  # D
        )

        self.context = ModbusServerContext(
            slaves=self.store,
            single=True
        )

    def sync_from_plc(self):
        """PLC → Modbus"""
        while True:
            # X → Discrete Input
            for i, v in enumerate(self.plc.mem.X):
                self.store.setValues(2, i, [int(v)])

            # Y → Coil 0～
            for i, v in enumerate(self.plc.mem.Y):
                self.store.setValues(1, i, [int(v)])

            # M → Coil 20～
            for i, v in enumerate(self.plc.mem.M):
                self.store.setValues(1, 20+i, [int(v)])

            # D → Holding Register
            for i, v in enumerate(self.plc.mem.D):
                self.store.setValues(3, i, [v])

    def start(self):
        threading.Thread(target=self.sync_from_plc, daemon=True).start()
        StartTcpServer(self.context, address=("0.0.0.0", 5020))
```

---

# ④ run_plc.py（Modbus統合版）

**最小変更のみ**します。

```python
# （前半は前回と同じ）

from modbus_server import ModbusBridge

def main():
    with open("plc.yaml") as f:
        plc_conf = yaml.safe_load(f)

    with open("ladder.yaml") as f:
        ladder_conf = yaml.safe_load(f)

    plc = PLC(plc_conf, ladder_conf)

    # Modbus起動
    modbus = ModbusBridge(plc)
    threading.Thread(target=modbus.start, daemon=True).start()

    # 仮想入力
    def input_simulator():
        time.sleep(2)
        plc.mem.X[0] = True
        time.sleep(2)
        plc.mem.X[0] = False
        time.sleep(4)
        plc.mem.X[1] = True

    threading.Thread(target=input_simulator, daemon=True).start()
    plc.run()
```

---

# ⑤ 起動方法

```bash
pip install pymodbus pyyaml
python run_plc.py
```

---

# ⑥ SCADA / クライアントからの確認

## 例：Y0を見る

* Coil
* アドレス：`0`
* 値：ON / OFF

## 例：M0を見る

* Coil
* アドレス：`20`

## 例：X0を見る

* Discrete Input
* アドレス：`0`

---

# 理解点

> modbusは外部ソフトではなく、plcユニットの機能

**Pythonで実装するコードががPLC + Modbusユニットそのもの**

