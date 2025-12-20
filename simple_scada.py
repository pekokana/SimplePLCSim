# simple_scada.py
import tkinter as tk
from pymodbus.client import ModbusTcpClient
import threading
import time

PLC_HOST = "localhost"
PLC_PORT = 15020
SCAN_INTERVAL = 0.5  # 秒

class SCADA(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Python SCADA GUI")
        self.geometry("400x300")

        self.client = ModbusTcpClient(PLC_HOST, port=PLC_PORT)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # GUI 要素
        self.x_vars = [tk.BooleanVar() for _ in range(4)]
        self.m_labels = [tk.Label(self, text=f"M{i}: False") for i in range(16)]
        self.y_labels = [tk.Label(self, text=f"Y{i}: False") for i in range(4)]

        # X 入力ボタン
        tk.Label(self, text="Inputs (X)").pack()
        for i, var in enumerate(self.x_vars):
            cb = tk.Checkbutton(self, text=f"X{i}", variable=var,
                                command=lambda idx=i: self.write_input(idx))
            cb.pack(anchor="w")

        # M ラベル
        tk.Label(self, text="Internal relays (M)").pack()
        for lbl in self.m_labels:
            lbl.pack(anchor="w")

        # Y ラベル
        tk.Label(self, text="Outputs (Y)").pack()
        for lbl in self.y_labels:
            lbl.pack(anchor="w")

        # バックグラウンドで PLC 状態を読み込む
        threading.Thread(target=self.update_loop, daemon=True).start()

    def write_input(self, idx):
        value = self.x_vars[idx].get()
        self.client.write_coil(idx, value)

    def update_loop(self):
        while True:
            try:
                # X 状態 (Discrete Inputs)
                rr = self.client.read_discrete_inputs(0, 4)
                if rr.isError():
                    continue
                for i, val in enumerate(rr.bits):
                    self.x_vars[i].set(val)

                # M + Y 状態 (Coils)
                rr2 = self.client.read_coils(0, 20)  # 0~19
                if not rr2.isError():
                    # Y0~Y3
                    for i in range(4):
                        self.y_labels[i].config(text=f"Y{i}: {rr2.bits[i]}")
                    # M0~M15
                    for i in range(16):
                        self.m_labels[i].config(text=f"M{i}: {rr2.bits[4+i]}")

            except Exception as e:
                print("SCADA read error:", e)

            time.sleep(SCAN_INTERVAL)

    def on_close(self):
        self.client.close()
        self.destroy()

if __name__ == "__main__":
    app = SCADA()
    app.mainloop()
