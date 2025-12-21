from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusServerContext,
    ModbusDeviceContext,
    ModbusSequentialDataBlock
)
import threading, time


class ModbusBridge:
    def __init__(self, plc, port, debug=False):
        self.plc = plc
        self.port = port
        self.debug = debug
        self.log = plc.log  # PLC の logger を使う

        self.log(f"[Modbus] server init port={port}")

        device = ModbusDeviceContext(
            di=ModbusSequentialDataBlock(0, [0] * 100),  # X
            co=ModbusSequentialDataBlock(0, [0] * 100),  # Y/M
            hr=ModbusSequentialDataBlock(0, [0] * 100),  # D
        )
        self.context = ModbusServerContext(devices=device, single=True)

        self._first_input = True

    def sync_from_plc(self):
        """PLC ←→ Modbus 同期"""
        self.log("[Modbus] sync thread started")

        while True:
            try:
                # --- X ← Client ---
                x_values = self.context[0].getValues(
                    1, 0, count=len(self.plc.mem.X)
                )

                if self._first_input and any(x_values):
                    self.log(f"[Modbus] first input detected X={x_values}")
                    self._first_input = False

                for i, v in enumerate(x_values):
                    self.plc.mem.X[i] = bool(v)

                # --- Y → Coil 20 ---
                for i, v in enumerate(self.plc.mem.Y):
                    self.context[0].setValues(1, 20 + i, [int(v)])

                # --- M → Coil 40 ---
                for i, v in enumerate(self.plc.mem.M):
                    self.context[0].setValues(1, 40 + i, [int(v)])

                # --- D → Holding Register ---
                for i, v in enumerate(self.plc.mem.D):
                    self.context[0].setValues(3, i, [v])

                if self.debug:
                    self.log("[Modbus][debug] sync done")

                time.sleep(0.1)

            except Exception as e:
                self.log(f"[Modbus][ERROR] {e}")
                time.sleep(1)

    def start(self):
        self.log(f"[Modbus] server START port={self.port}")
        threading.Thread(target=self.sync_from_plc, daemon=True).start()
        StartTcpServer(self.context, address=("0.0.0.0", self.port))
