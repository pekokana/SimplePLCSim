from pymodbus.client import ModbusTcpClient
import time

# PLCごとのポート設定
plcs = {
    "PLC_A": 15020,
    "PLC_B": 15021
}

# 接続初期化
clients = {}
for name, port in plcs.items():
    clients[name] = ModbusTcpClient('localhost', port=port)
    clients[name].connect()
    print(f"{name} connected on port {port}")

try:
    t = 0
    while True:
        t += 1

        # 例: PLC_A の X0 を1秒間隔でON/OFF
        state = t % 2 == 0
        clients["PLC_A"].write_coil(0, state)  # X0
        clients["PLC_B"].write_coil(0, not state)  # X0 逆に
        print(f"[SCADA] Set PLC_A X0={state}, PLC_B X0={not state}")

        # PLCのY0を読み取って表示
        for name, client in clients.items():
            rr = client.read_coils(0, 4)
            if rr.isError():
                print(f"[SCADA] {name} read error")
            else:
                print(f"[SCADA] {name} Y0-Y3: {rr.bits[:4]}")

        time.sleep(1)

finally:
    for name, client in clients.items():
        client.close()
