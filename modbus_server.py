from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusServerContext,
    ModbusDeviceContext,
    ModbusSequentialDataBlock
)
import threading
import time


# -----------------------------
# Chaos Context Wrapper
# -----------------------------
class ChaosSlaveContext:
    """SlaveContextをラップし、値の取得・設定時に遅延を注入する"""
    def __init__(self, original_context, bridge):
        self.original = original_context
        self.bridge = bridge

    def getValues(self, fc, address, count=1):
        # 外部からのリクエスト（Orchestrator以外など）に対して遅延を発生させる
        # sync_from_plc 内部からの呼び出しと区別するため、フラグを確認
        if self.bridge.latency_sec > 0:
            time.sleep(self.bridge.latency_sec)
        return self.original.getValues(fc, address, count)

    def setValues(self, fc, address, values):
        if self.bridge.latency_sec > 0:
            time.sleep(self.bridge.latency_sec)
        self.original.setValues(fc, address, values)

    def validate(self, fc, address, count=1):
        return self.original.validate(fc, address, count)

class ChaosServerContext:
    """ModbusServerContextをラップし、ChaosSlaveContextを返す"""
    def __init__(self, original_server_context, bridge):
        self.original = original_server_context
        self.bridge = bridge

    def __getitem__(self, slave_id):
        # slave_id に対応するコンテキストをラップして返す
        return ChaosSlaveContext(self.original[slave_id], self.bridge)

    def __setitem__(self, slave_id, context):
        self.original[slave_id] = context

# -----------------------------
# Modbus Bridge
# -----------------------------
class ModbusBridge:
    def __init__(self, plc, port, debug=False):
        self.plc = plc
        self.port = port
        self.debug = debug
        self.log = plc.log

        # --- Chaos Flag ---
        self.latency_sec = 0  # 遅延時間（秒）。0なら遅延なし

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

        # self.context = ModbusServerContext(devices=device, single=True)

        # オリジナルのコンテキストを作成し、Chaosコンテキストでラップする
        raw_context = ModbusServerContext(devices=device, single=True)
        self.context = ChaosServerContext(raw_context, self)

        self._first_input = True

    # -------------------------------------------------
    # PLC <-> Modbus 同期
    # -------------------------------------------------
    def sync_from_plc(self):
        self.log("[Modbus] sync thread started")

        # 内部同期用のアクセスでは遅延させないため、一時的にコンテキストを直接参照する
        # (self.context.original を使って遅延をバイパス)
        raw_slave_context = self.context.original[0]

        while True:
            try:
                # ---------- X ← Client ----------
                x_values = raw_slave_context.getValues(1, 0, count=len(self.plc.mem.X))

                if self._first_input and any(x_values):
                    self.log(f"[Modbus] first input detected X={x_values}")
                    self._first_input = False

                for i, v in enumerate(x_values):
                    self.plc.mem.X[i] = bool(v)

                # ---------- Y → Coil 20 ----------
                for i, v in enumerate(self.plc.mem.Y):
                    raw_slave_context.setValues(1, 20 + i, [int(v)])

                # ---------- M → Coil 40 ----------
                for i, v in enumerate(self.plc.mem.M):
                    raw_slave_context.setValues(1, 40 + i, [int(v)])

                # ---------- D → HR 0 ----------
                for i, v in enumerate(self.plc.mem.D):
                    raw_slave_context.setValues(3, i, [int(v)])

                # --- システムレジスタの同期 ---
                sys = self.plc.mem.sys
                raw_slave_context.setValues(3, self.HR_SYS_BASE + 0, [sys.heartbeat])
                raw_slave_context.setValues(3, self.HR_SYS_BASE + 1, [sys.scan_count & 0xFFFF])
                raw_slave_context.setValues(3, self.HR_SYS_BASE + 2, [sys.uptime_sec])

                # --- カオス設定の読み取り (HR 10005 を遅延設定用に使用) ---
                # Orchestratorなどのクライアントがこのアドレスに数値を書き込むことで遅延を操作できる
                chaos_val = raw_slave_context.getValues(3, self.HR_SYS_BASE + 5, count=1)[0]
                if chaos_val != self.latency_sec:
                    self.latency_sec = chaos_val
                    if self.latency_sec > 0:
                        self.log(f"[Modbus][CHAOS] Latency injected: {self.latency_sec}s")
                    else:
                        self.log(f"[Modbus][CHAOS] Latency removed")

                if self.debug:
                    self.log("[Modbus][debug] sync done")

                time.sleep(0.1)

            except Exception as e:
                self.log(f"[Modbus][ERROR] {e}")
                time.sleep(1)

            #     # ---------- X ← Client ----------
            #     x_values = self.context[0].getValues(
            #         1, 0, count=len(self.plc.mem.X)
            #     )

            #     if self._first_input and any(x_values):
            #         self.log(f"[Modbus] first input detected X={x_values}")
            #         self._first_input = False

            #     for i, v in enumerate(x_values):
            #         self.plc.mem.X[i] = bool(v)

            #     # ---------- Y → Coil 20 ----------
            #     for i, v in enumerate(self.plc.mem.Y):
            #         self.context[0].setValues(1, 20 + i, [int(v)])

            #     # ---------- M → Coil 40 ----------
            #     for i, v in enumerate(self.plc.mem.M):
            #         self.context[0].setValues(1, 40 + i, [int(v)])

            #     # ---------- D → HR 0 ----------
            #     for i, v in enumerate(self.plc.mem.D):
            #         self.context[0].setValues(3, i, [int(v)])

            #     # -------------------------------------------------
            #     # system register → HR 10000〜
            #     # -------------------------------------------------
            #     sys = self.plc.mem.sys

            #     self.context[0].setValues(
            #         3, self.HR_SYS_BASE + 0, [sys.heartbeat]
            #     )
            #     self.context[0].setValues(
            #         3, self.HR_SYS_BASE + 1, [sys.scan_count & 0xFFFF]
            #     )
            #     self.context[0].setValues(
            #         3, self.HR_SYS_BASE + 2, [sys.uptime_sec]
            #     )

            #     if self.debug:
            #         self.log("[Modbus][debug] sync done")

            #     time.sleep(0.1)

            # except Exception as e:
            #     self.log(f"[Modbus][ERROR] {e}")
            #     time.sleep(1)

    # -------------------------------------------------
    # Start Server
    # -------------------------------------------------
    def start(self):
        self.log(f"[Modbus] server START port={self.port}")
        threading.Thread(target=self.sync_from_plc, daemon=True).start()
        # StartTcpServer(self.context, address=("0.0.0.0", self.port))
        # self.context (Chaosラップ済み) をサーバーに渡す
        StartTcpServer(self.context.original, address=("0.0.0.0", self.port))
