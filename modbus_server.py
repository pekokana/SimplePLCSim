from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusServerContext, ModbusDeviceContext, ModbusSequentialDataBlock
import threading, time

class ModbusBridge:
    def __init__(self, plc, port):
        print("modbus_server START")

        self.plc = plc
        self.port = port

        # ディスクリート入力は X のみ
        device = ModbusDeviceContext(
            di=ModbusSequentialDataBlock(0, [0] * 100),  # X入力
            co=ModbusSequentialDataBlock(0, [0] * 100),  # Y/M出力
            hr=ModbusSequentialDataBlock(0, [0] * 100),  # Dレジスタ
        )
        self.context = ModbusServerContext(devices=device, single=True)

    def sync_from_plc(self):
        """PLC ← Modbus Client 書き込み値同期"""
        while True:
            # Coil 0～ を X に反映
            x_values = self.context[0].getValues(1, 0, count=len(self.plc.mem.X))  # Function 1 = Coil
            for i, v in enumerate(x_values):
                self.plc.mem.X[i] = bool(v)

            # Y → Coil 20～
            for i, v in enumerate(self.plc.mem.Y):
                self.context[0].setValues(1, 20 + i, [int(v)])

            # M → Coil 40～
            for i, v in enumerate(self.plc.mem.M):
                self.context[0].setValues(1, 40 + i, [int(v)])

            # D → Holding Register
            for i, v in enumerate(self.plc.mem.D):
                self.context[0].setValues(3, i, [v])

            time.sleep(0.1)


    def start(self):
        threading.Thread(target=self.sync_from_plc, daemon=True).start()
        StartTcpServer(self.context, address=("0.0.0.0", self.port))
