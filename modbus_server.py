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
        # 本来の処理（遅延注入など）
        if self.bridge.latency_sec > 0:
            time.sleep(self.bridge.latency_sec)
        self.original.setValues(fc, address, values)

    # 必須メソッドの委譲
    def validate(self, fc, address, count=1):
        return self.original.validate(fc, address, count)

    # Pymodbus内部で期待される全メソッド/属性を original に転送する
    def __getattr__(self, name):
        return getattr(self.original, name)

    def __setattr__(self, name, value):
        # originalの属性を更新しようとした場合も転送する
        if name in ('original', 'bridge'):
            object.__setattr__(self, name, value)
        else:
            setattr(self.original, name, value)

# --- 1. 書き込みを監視するカスタムブロッククラスを定義 ---
class InjectedDataBlock(ModbusSequentialDataBlock):
    def __init__(self, address, values, bridge, dev_type):
        super().__init__(address, values)
        self.bridge = bridge
        self.dev_type = dev_type
        self.is_syncing = False  # 同期中かどうかのフラグ

    def setValues(self, address, values):
        # 最後に親（Modbusの台帳）の値を更新
        super().setValues(address, values)

        # 同期スレッドからの呼び出し（is_syncing=True）なら、PLCへの反映とログ出力をスキップ
        if self.is_syncing:
            return

        # 2. 物理入力(X)への反映ロジック
        if self.dev_type == 'CO':
            # Pymodbus 3.x の SequentialDataBlock では、
            # address は既に 0-based のインデックスで渡されることが多いため -1 は不要。
            # もしこれでズレる場合は address をそのまま使います。
            base_idx = address - 1
            

            for i, v in enumerate(values):
                target_idx = base_idx + i
                # self.bridge.log(f"setValues param values:{i} > {v} | target_idx:{target_idx}")
                
                # PLC の X メモリの範囲内かチェック
                if 0 <= target_idx < len(self.bridge.plc.mem.X):
                    old_v = self.bridge.plc.mem.X[target_idx]
                    new_v = bool(v)
                    
                    if old_v != new_v:
                        self.bridge.plc.mem.X[target_idx] = new_v
                        self.bridge.log(f"[SIM_INJECT] Physical Signal: X{target_idx} = {new_v}")


class ChaosServerContext:
    def __init__(self, original_server_context, bridge):
        self.original = original_server_context
        self.bridge = bridge

    # --- Pymodbus内部が IDを指定してスレーブを取得する時に呼ばれる ---
    def __getitem__(self, slave_id):
        # どのID（0 or 1）で来ても、確実にラップして返す
        try:
            raw_slave = self.original[slave_id]
        except:
            # 取得失敗時は 1番(default) を試す
            raw_slave = self.original[1] 
        
        return ChaosSlaveContext(raw_slave, self.bridge)

    # --- Pymodbus 3.x が内部で .slaves や .devices を直接参照する場合の対策 ---
    @property
    def slaves(self):
        # 自分が自分を辞書のように振る舞わせる
        return self

    @property
    def devices(self):
        return self

    # dictのように振る舞うための最小限の実装
    def __contains__(self, key):
        return True # どんなIDが来ても「あるよ」と答える

    def __iter__(self):
        return iter([1]) # ID 1 がメインであることを示す

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
            di=ModbusSequentialDataBlock(1, [0] * x_count), # X用 (FC2)
            co=InjectedDataBlock(1, [0] * co_size, self, 'CO'), # Y, M用 (FC1)
            hr=ModbusSequentialDataBlock(1, [0] * hr_size), # D, Sys用 (FC3)
        )

        # 1. 同期スレッドが直接触るための「生のデバイス」を保持
        self.raw_device = device  

        # 2. サーバー用のコンテキストを作成
        # 引数名は 'devices' を使用し、辞書形式で ID 1 に割り当てます
        raw_context = ModbusServerContext(devices={1: device}, single=False)
        
        # 3. 自作の ChaosServerContext で包む
        self.context = ChaosServerContext(raw_context, self)


    # -------------------------------------------------
    # PLC <-> Modbus 同期
    # -------------------------------------------------
    def sync_from_plc(self):
        self.log("[Modbus] sync thread started")

        # Mansion全体を通さず、保存しておいた「部屋(Device)」を直接操作する
        raw_slave_context = self.raw_device

        while True:
            try:

                # 同期開始。InjectedDataBlockのフラグを立ててログ出力を抑制する
                # raw_device.store['c'] が CO (InjectedDataBlock) インスタンスを指します
                self.raw_device.store['c'].is_syncing = True

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
                # Mmodbusの取り扱い解釈誤りのため以下のように修正
                # deicesimが直接書き換えたPLC.m.xの値を、modbusの台帳(DI)に反映する
                # これにより、外部(orchestratorなど)から入力状況が見えるようになる想定
                # --------------以下、修正前のコード -----------------
                # res = raw_slave_context.getValues(2, 1, count=len(self.plc.mem.X))
                # if isinstance(res, list):
                #     for i, v in enumerate(res):
                #         if i < len(self.plc.mem.X):
                #             self.plc.mem.X[i] = bool(v)
                # --------------以下、修正後のコード-------------------
                for i, v in enumerate(self.plc.mem.X):
                    raw_slave_context.setValues(2, i, [int(v)])

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

                # 同期終了。フラグを戻す
                self.raw_device.store['c'].is_syncing = False

                time.sleep(0.1)

            except Exception as e:
                # エラー発生時も念のためフラグを戻す
                if hasattr(self.raw_device.store['c'], 'is_syncing'):
                    self.raw_device.store['c'].is_syncing = False

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
