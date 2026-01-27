from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusServerContext,
    ModbusDeviceContext,
    ModbusSequentialDataBlock
)
import threading
import time
import sys


# -----------------------------
# Chaos Context Wrapper
# -----------------------------
class ChaosSlaveContext:
    """SlaveContextをラップし、値の取得・設定時に遅延を注入する"""
    def __init__(self, original_context, bridge):
        self.log = bridge.log
        # 内部プロパティへの直接アクセスで無限ループを防ぐため
        # __setattr__ を介さずに設定
        object.__setattr__(self, 'original', original_context)
        object.__setattr__(self, 'bridge', bridge)


    def getValues(self, fc, address, count=1):
        # どのFCが来ているかログを出す
        print(f"[DEBUG] ChaosSlaveContext.getValues: fc={fc}, addr={address}, count={count}",flush=True)

        if self.bridge.latency_sec > 0:
            time.sleep(self.bridge.latency_sec)

        return self.original.getValues(fc, address, count)

    def setValues(self, fc, address, values):
        print(f"[DEBUG] ChaosSlaveContext.setValues: fc={fc}, addr={address}, values={values}")


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
        self.log = bridge.log
        self.dev_type = dev_type
        self.is_syncing = False  # 同期中かどうかのフラグ

    def getValues(self, address, count=1):
        # サーバーからの読み出し要求をログに出す
        # address: プロトコルオフセット (Mなら100以上のはず)
        # count: 読み出し点数
        v = super().getValues(address, count)
        # print(f"[DEBUG-GET] type:{self.dev_type} addr:{address} count:{count} -> {v}")
        return v

    def setValues(self, address, values):
        # 最後に親（Modbusの台帳）の値を更新
        super().setValues(address, values)


        # 同期スレッドからの呼び出し（is_syncing=True）なら、PLCへの反映とログ出力をスキップ
        if self.is_syncing:
            return
        # 2. 物理入力(X)への反映ロジック
        if self.dev_type == 'CO':

            for i, v in enumerate(values):
                offset = address + i

                # Y: 論理1-100 (オフセット0-99)
                if 0 <= offset < 100:
                    if offset < len(self.bridge.plc.mem.Y):
                        self.bridge.plc.mem.Y[offset] = bool(v)
                # M: 論理101-1000 (オフセット100-999)
                elif 100 <= offset < 1000:
                    m_idx = offset - 100
                    if m_idx < len(self.bridge.plc.mem.M):
                        self.bridge.plc.mem.M[m_idx] = bool(v)
                # X: SIM_INJECT用隠しアドレス(オフセット 2000)
                elif 2000 <= offset < 2100:
                    x_idx = offset - 2000 - 1
                    if x_idx < len(self.bridge.plc.mem.X):
                        self.bridge.plc.mem.X[x_idx] = bool(v)
       
        elif self.dev_type == 'HR':
            for i, v in enumerate(values):
                offset = address + i

                # ==========================
                # CHAOS FREEZE CONTROL
                # ==========================
                if offset == self.bridge.SYS_CHAOS_FREEZE_CTRL:
                    self.bridge.plc.frozen = bool(v)
                    self.log(f"[CHAOS] PLC FREEZE {'ON' if v else 'OFF'}")
                    continue  # ★Dレジスタとして扱わない

                if 0 <= offset < self.bridge.OFFS_SYS_BASE: # 512未満（Dレジスタ領域）
                    if offset < len(self.bridge.plc.mem.D):
                        self.bridge.plc.mem.D[offset] = v

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

        # --- 新しいアドレスマップ定義 (プロトコルオフセット) ---
        self.OFFS_X_START = 0      # 10001〜 (FC2)
        self.OFFS_X_COIL_SIM_INJECT_START = 2000 # Device / IODeviceからのX(Discrete Input)に対するSIM_INJECTをするための隠しアドレス
        self.OFFS_Y_START = 0      # 00001〜 (FC1/5/15)
        self.OFFS_M_START = 100    # 00101〜 (FC1/5/15)
        self.OFFS_D_START = 0      # 40001〜 (FC3/6/16)
        self.OFFS_SYS_BASE = 512   # 40513〜 (FC3)
        self.SYS_CHAOS_LATENCY = self.OFFS_SYS_BASE + 3
        self.SYS_CHAOS_FREEZE_CTRL = self.OFFS_SYS_BASE + 4  # Chaos Ferrze制御用


        x_count = len(self.plc.mem.X)
        y_count = len(self.plc.mem.Y)
        m_count = len(self.plc.mem.M)
        d_count = len(self.plc.mem.D)

        self.log(f"[Modbus] mapping: X=10001-, Y=1-, M=101-, D=40001-, Sys=40513-")

        # データブロックのサイズ確保
        # DI: X用 (10001〜)
        # self.log(f"[DEBUG] di_block size: {self.OFFS_X_START + x_count}") # ここで 10 以上の数値が出るか確認
        di_block = ModbusSequentialDataBlock(0, [0] * (self.OFFS_X_START + x_count))
        # CO: YとM用 (1〜)
        # co_block = InjectedDataBlock(0, [0] * (self.OFFS_M_START + m_count), self, 'CO')
        co_block = InjectedDataBlock(0, [0] * (self.OFFS_X_COIL_SIM_INJECT_START + x_count), self, 'CO')
        # HR: DとSystem用 (40001〜)
        hr_block = InjectedDataBlock(0, [0] * (self.OFFS_SYS_BASE + 20), self, 'HR')
        device = ModbusDeviceContext(di=di_block, co=co_block, hr=hr_block)

        # 1. 同期スレッドが直接触るための「生のデバイス」を保持
        self.raw_device = device  

        # 2. サーバー用のコンテキストを作成
        # 引数名は 'devices' を使用し、辞書形式で ID 1 に割り当てます
        self.raw_context = ModbusServerContext(devices={1: device}, single=False)
        # raw_context = ModbusServerContext(devices=device, single=True)
        
        # 3. 自作の ChaosServerContext で包む
        self.context = ChaosServerContext(self.raw_context, self)

        self.log("======= Modbus Memory Allocation Info =======")
        for key, block in self.raw_device.store.items():
            # 各ブロックに割り当てられたリストの長さを取得
            allocated_size = len(block.values) if hasattr(block, 'values') else "N/A"
            
            # 役割の判定（ソースのマップ情報に基づく）
            role = ""
            if key in ['d', 'di']: role = "X (Discrete Inputs)"
            elif key in ['c', 'co']: role = "Y/M + X<SIM_INJECT(Coils)"
            elif key in ['h', 'hr']: role = "D/System (Holding Registers)"
            
            self.log(f"StoreKey: '{key}' | Role: {role:25} | Size: {allocated_size}")

    # -------------------------------------------------
    # PLC <-> Modbus 同期
    # -------------------------------------------------
    def sync_from_plc(self):
        """
        Synchronize PLC system values into Modbus registers.
        This must stop when PLC CPU is frozen.
        """
        self.log("[Modbus] sync thread started")

        while True:
            try:
                # chaos delay対応
                if self.latency_sec > 0:
                    time.sleep(self.latency_sec)

                # 同期開始。InjectedDataBlockのフラグを立ててログ出力を抑制する
                self.raw_device.store['c'].is_syncing = True
                self.raw_device.store['h'].is_syncing = True # HRも同期フラグを管理できるようにする場合は追加
                # print(f"[debug--] {self.raw_device.store}")
                if 'd' in self.raw_device.store:
                    # print(f"[debug - flag]if 'd' in self.raw_device.store:")
                    self.raw_device.store['d'].is_syncing = True

                # if self._first_input:
                #     self._first_input = False
                #     self.raw_device.setValues(3, self.OFFS_SYS_BASE + 3, [0])
                #     self.raw_device.setValues(3, self.OFFS_SYS_BASE + 4, [0])

                # 1-2. chaos freeze設定 (System領域のオフセット4 + 512 = 516 を使用)
                chaos_freezeres = self.raw_device.getValues(3, self.OFFS_SYS_BASE + 4, count=1)

                if isinstance(chaos_freezeres, list) and len(chaos_freezeres) > 0:
                    new_freeze = chaos_freezeres[0]
                    if new_freeze == 0: # Flase | Freezeではない
                        self.plc.frozen = False
                    elif new_freeze == 1: # True | Freezeである
                        self.plc.frozen = True
                    else: # False | 想定外値の場合はFreezeではない扱いとする
                        self.plc.frozen = False

                # =============================
                # PLC freeze ガード 
                # =============================
                if self.plc.frozen:
                    # freeze 中は一切同期しない
                    time.sleep(0.1)
                    continue

                # 1. chaos delay設定 (System領域のオフセット3 + 512 = 515 を使用)
                chaos_res = self.raw_device.getValues(3, self.OFFS_SYS_BASE + 3, count=1)

                if isinstance(chaos_res, list) and len(chaos_res) > 0:
                    new_latency = chaos_res[0]
                    if new_latency > 0:
                        if new_latency != self.latency_sec:
                            self.latency_sec = new_latency
                            self.log(f"!!! [CHAOS] Latency: {self.latency_sec}s !!!")


                # 2. X -> DI (オフセット0〜)
                for i, v in enumerate(self.plc.mem.X):
                    self.raw_device.setValues(2, self.OFFS_X_START + i, [int(v)])
                    # SIM_INJECT用の隠しコイルアドレスへの値反映
                    # self.raw_device.setValues(1, self.OFFS_X_COIL_SIM_INJECT_START + i - 1, [int(v)]) #@@@
                    self.raw_device.setValues(1, self.OFFS_X_COIL_SIM_INJECT_START + i, [int(v)])

                # 3. Y/M -> CO (Yはオフセット0〜, Mはオフセット100〜)
                for i, v in enumerate(self.plc.mem.Y):
                    self.raw_device.setValues(1, self.OFFS_Y_START + i, [int(v)])
                for i, v in enumerate(self.plc.mem.M):
                    self.raw_device.setValues(1, self.OFFS_M_START + i, [int(v)])

                # 4. D -> HR (オフセット0〜511 までに制限する)
                for i, v in enumerate(self.plc.mem.D):
                    if i >= self.OFFS_SYS_BASE: # 512 を超えたら終了
                        break
                    self.raw_device.setValues(3, self.OFFS_D_START + i, [int(v)])

                # 5. System -> HR (オフセット512〜)
                sys = self.plc.mem.sys
                self.raw_device.setValues(3, self.OFFS_SYS_BASE + 0, [sys.heartbeat & 0xFFFF])
                self.raw_device.setValues(3, self.OFFS_SYS_BASE + 1, [sys.scan_count & 0xFFFF])
                self.raw_device.setValues(3, self.OFFS_SYS_BASE + 2, [sys.uptime_sec & 0xFFFF])

                # 同期終了。フラグを戻す
                self.raw_device.store['c'].is_syncing = False
                self.raw_device.store['h'].is_syncing = False
                self.raw_device.store['d'].is_syncing = False
                time.sleep(0.05)

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
        self.log(f"[BOOT] initial freeze flag = {self.plc.frozen}")
        self.log(f"[Modbus] server START port={self.port}")
        threading.Thread(target=self.sync_from_plc, daemon=True).start()
        # self.context (Chaosラップ済み) をサーバーに渡す
        # StartTcpServer(self.context.original, address=("0.0.0.0", self.port))
        StartTcpServer(self.context, address=("0.0.0.0", self.port))
