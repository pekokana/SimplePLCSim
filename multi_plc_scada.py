import tkinter as tk
from pymodbus.client import ModbusTcpClient
import threading
import time

SCAN_INTERVAL = 0.2  # PLC状態取得間隔

class PLCGUI:
    def __init__(self, master, name, host, port, X_count=4, Y_count=4, M_count=16):
        self.master = master
        self.name = name
        self.client = ModbusTcpClient(host, port=port)
        self.X_count = X_count
        self.Y_count = Y_count
        self.M_count = M_count

        # GUIフレーム
        self.frame = tk.LabelFrame(master, text=name)
        self.frame.pack(padx=5, pady=5, fill="x")

        # X 入力
        tk.Label(self.frame, text="X Inputs").grid(row=0, column=0)
        self.X_vars = []
        for i in range(X_count):
            var = tk.IntVar()
            cb = tk.Checkbutton(self.frame, text=f"X{i}", variable=var,
                                command=lambda idx=i: self.set_X(idx))
            cb.grid(row=1, column=i)
            self.X_vars.append(var)

        # Y 出力表示
        tk.Label(self.frame, text="Y Outputs").grid(row=2, column=0)
        self.Y_vars = []
        for i in range(Y_count):
            var = tk.StringVar()
            lbl = tk.Label(self.frame, text=f"Y{i}", bg="red", width=4)
            lbl.grid(row=3, column=i, padx=2)
            self.Y_vars.append(lbl)

        # M 内部リレー表示
        tk.Label(self.frame, text="M Internal").grid(row=4, column=0)
        self.M_vars = []
        for i in range(M_count):
            lbl = tk.Label(self.frame, text=f"M{i}", bg="red", width=4)
            lbl.grid(row=5 + i//8, column=i%8, padx=2)
            self.M_vars.append(lbl)

        # PLC状態取得スレッド
        threading.Thread(target=self.update_loop, daemon=True).start()

    def set_X(self, idx):
        """X入力をPLCに反映"""
        self.client.write_coil(address=idx, value=self.X_vars[idx].get())

    def update_loop(self):
        """PLC状態を定期取得してGUI反映"""
        while True:
            # Y
            for i in range(self.Y_count):
                rr = self.client.read_coils(address=i, count=1)
                if rr.isError():
                    continue
                val = rr.bits[0]
                self.Y_vars[i].config(bg="green" if val else "red")

            # M
            for i in range(self.M_count):
                rr = self.client.read_coils(address=20 + i, count=1)  # MはCoil20以降
                if rr.isError():
                    continue
                val = rr.bits[0]
                self.M_vars[i].config(bg="green" if val else "red")

            time.sleep(SCAN_INTERVAL)


# -----------------------------
# 複数PLC起動例
# -----------------------------
def main():
    root = tk.Tk()
    root.title("Multi PLC SCADA GUI")

    # PLC設定例
    plc_configs = [
        {"name": "PLC_A", "host": "localhost", "port": 15020},
        {"name": "PLC_B", "host": "localhost", "port": 15021},
    ]

    for cfg in plc_configs:
        PLCGUI(root, cfg["name"], cfg["host"], cfg["port"])

    root.mainloop()


if __name__ == "__main__":
    main()
