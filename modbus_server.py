from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusServerContext,
    ModbusDeviceContext,
    ModbusSequentialDataBlock
)
import threading
import time


# -----------------------------
# Modbus Bridge
# -----------------------------
class ModbusBridge:
    def __init__(self, plc, port, debug=False):
        self.plc = plc
        self.port = port
        self.debug = debug
        self.log = plc.log

        self.log(f"[Modbus] server init port={port}")

        # -------------------------------------------------
        # Holding Register を拡張（system 用を含む）
        # -------------------------------------------------
        self.HR_USER_SIZE = 100           # D レジスタ用
        self.HR_SYS_BASE = 10000          # system register base
        self.HR_SYS_SIZE = 10             # 余裕を持たせる

        device = ModbusDeviceContext(
            di=ModbusSequentialDataBlock(0, [0] * 100),   # X
            co=ModbusSequentialDataBlock(0, [0] * 100),   # Y/M
            hr=ModbusSequentialDataBlock(
                0,
                [0] * (self.HR_USER_SIZE + self.HR_SYS_BASE + self.HR_SYS_SIZE)
            ),
        )

        self.context = ModbusServerContext(devices=device, single=True)
        self._first_input = True

    # -------------------------------------------------
    # PLC <-> Modbus 同期
    # -------------------------------------------------
    def sync_from_plc(self):
        self.log("[Modbus] sync thread started")

        while True:
            try:
                # ---------- X ← Client ----------
                x_values = self.context[0].getValues(
                    1, 0, count=len(self.plc.mem.X)
                )

                if self._first_input and any(x_values):
                    self.log(f"[Modbus] first input detected X={x_values}")
                    self._first_input = False

                for i, v in enumerate(x_values):
                    self.plc.mem.X[i] = bool(v)

                # ---------- Y → Coil 20 ----------
                for i, v in enumerate(self.plc.mem.Y):
                    self.context[0].setValues(1, 20 + i, [int(v)])

                # ---------- M → Coil 40 ----------
                for i, v in enumerate(self.plc.mem.M):
                    self.context[0].setValues(1, 40 + i, [int(v)])

                # ---------- D → HR 0 ----------
                for i, v in enumerate(self.plc.mem.D):
                    self.context[0].setValues(3, i, [int(v)])

                # -------------------------------------------------
                # system register → HR 10000〜
                # -------------------------------------------------
                sys = self.plc.mem.sys

                self.context[0].setValues(
                    3, self.HR_SYS_BASE + 0, [sys.heartbeat]
                )
                self.context[0].setValues(
                    3, self.HR_SYS_BASE + 1, [sys.scan_count & 0xFFFF]
                )
                self.context[0].setValues(
                    3, self.HR_SYS_BASE + 2, [sys.uptime_sec]
                )

                if self.debug:
                    self.log("[Modbus][debug] sync done")

                time.sleep(0.1)

            except Exception as e:
                self.log(f"[Modbus][ERROR] {e}")
                time.sleep(1)

    # -------------------------------------------------
    # Start Server
    # -------------------------------------------------
    def start(self):
        self.log(f"[Modbus] server START port={self.port}")
        threading.Thread(target=self.sync_from_plc, daemon=True).start()
        StartTcpServer(self.context, address=("0.0.0.0", self.port))
