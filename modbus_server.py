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
        # 内部プロパティへの直接アクセスで無限ループを防ぐため
        # __setattr__ を介さずに設定
        object.__setattr__(self, 'original', original_context)
        object.__setattr__(self, 'bridge', bridge)

    def getValues(self, fc, address, count=1):
        if self.bridge.latency_sec > 0:
            time.sleep(self.bridge.latency_sec)
        return self.original.getValues(fc, address, count)

    def setValues(self, fc, address, values):
        if self.bridge.latency_sec > 0:
            time.sleep(self.bridge.latency_sec)
        self.original.setValues(fc, address, values)

    # Pymodbus内部で期待される全メソッド/属性を original に転送する
    def __getattr__(self, name):
        return getattr(self.original, name)

    def __setattr__(self, name, value):
        # originalの属性を更新しようとした場合も転送する
        if name in ('original', 'bridge'):
            object.__setattr__(self, name, value)
        else:
            setattr(self.original, name, value)

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

        self.latency_sec = 0  
        self._first_input = True

        # --- アドレスマップの定義 (ここを基準にすべて自動計算される) ---
        self.ADDR_Y_START = 0      # Y (Coil) は 0 から開始
        self.ADDR_M_START = 1000   # M (Coil) は 1000 から開始 (干渉防止)
        self.ADDR_D_START = 0      # D (Register) は 0 から開始
        self.HR_SYS_BASE  = 10000  # システム情報は 10000 から開始

        # --- 重要：PLCの実体メモリからサイズを自動取得する ---
        x_count = len(self.plc.mem.X)  # 例: 100
        y_count = len(self.plc.mem.Y)  # 例: 100
        m_count = len(self.plc.mem.M)  # 例: 1000
        d_count = len(self.plc.mem.D)  # 例: 1000

        self.log(f"[Modbus] server init: X={x_count}, Y={y_count}, M={m_count}, D={d_count}")

        # --- 名簿（データブロック）のサイズ計算 ---
        # 必要な長さは「開始アドレス + 実際の個数」
        co_size = self.ADDR_M_START + m_count 
        hr_size = self.HR_SYS_BASE + 20 # システム領域分を確保

        # --- 受付名簿（データブロック）の作成 ---
        device = ModbusDeviceContext(
            di=ModbusSequentialDataBlock(0, [0] * x_count), # X用 (FC2)
            co=ModbusSequentialDataBlock(0, [0] * co_size), # Y, M用 (FC1)
            hr=ModbusSequentialDataBlock(0, [0] * hr_size), # D, Sys用 (FC3)
        )

        # あとは共通
        raw_context = ModbusServerContext(devices=device, single=True)
        self.context = ChaosServerContext(raw_context, self)
        self._first_input = True


    # -------------------------------------------------
    # PLC <-> Modbus 同期
    # -------------------------------------------------
    def sync_from_plc(self):
        self.log("[Modbus] sync thread started")
        # 内部同期は遅延させないため original を直接使う
        raw_slave_context = self.context.original[0]

        while True:
            try:
                # ---------- 1. カオス設定の読み取り ----------
                # HR 10005 を遅延設定用に使用。ここを外部(Python等)から書き換えると遅延が始まる
                chaos_res = raw_slave_context.getValues(3, self.HR_SYS_BASE + 5, count=1)
                if isinstance(chaos_res, list):
                    new_latency = chaos_res[0]
                    if new_latency != self.latency_sec:
                        self.latency_sec = new_latency
                        if self.latency_sec > 0:
                            self.log(f"!!! [CHAOS] Latency Mode Active: {self.latency_sec}s !!!")
                        else:
                            self.log("[CHAOS] Latency Mode Disabled")

                # ---------- 2. X ← Client (FC2) ----------
                res = raw_slave_context.getValues(2, 0, count=len(self.plc.mem.X))
                if isinstance(res, list):
                    for i, v in enumerate(res):
                        if i < len(self.plc.mem.X):
                            self.plc.mem.X[i] = bool(v)

                # ---------- 3. Y/M/D 送信処理 ----------
                # 定義した START アドレスを基準にループ
                # Y (Coil 0〜)
                for i, v in enumerate(self.plc.mem.Y):
                    raw_slave_context.setValues(1, self.ADDR_Y_START + i, [int(v)])
                
                # M (Coil 1000〜)
                for i, v in enumerate(self.plc.mem.M):
                    raw_slave_context.setValues(1, self.ADDR_M_START + i, [int(v)])
                
                # D (HR 0〜)
                for i, v in enumerate(self.plc.mem.D):
                    raw_slave_context.setValues(3, self.ADDR_D_START + i, [int(v)])
                    
                # ---------- 4. システムレジスタ更新 ----------
                sys = self.plc.mem.sys
                raw_slave_context.setValues(3, self.HR_SYS_BASE + 0, [sys.heartbeat])
                raw_slave_context.setValues(3, self.HR_SYS_BASE + 1, [sys.scan_count & 0xFFFF])
                raw_slave_context.setValues(3, self.HR_SYS_BASE + 2, [sys.uptime_sec])

                time.sleep(0.1)

            except Exception as e:
                import traceback
                self.log(f"[Modbus][ERROR] {e}\n{traceback.format_exc()}")
                time.sleep(1)

    # -------------------------------------------------
    # Start Server
    # -------------------------------------------------
    def start(self):
        self.log(f"[Modbus] server START port={self.port}")
        threading.Thread(target=self.sync_from_plc, daemon=True).start()
        # self.context (Chaosラップ済み) をサーバーに渡す
        # StartTcpServer(self.context.original, address=("0.0.0.0", self.port))
        StartTcpServer(self.context, address=("0.0.0.0", self.port))
