from pymodbus.client import ModbusTcpClient
import time

# PLCシミュレータに接続
client = ModbusTcpClient('localhost', port=15020)
print("connect ok modbus_server")


try:
    while True:
        # X0をONにしてPLCに入力
        print("X0 - ON")
        client.write_coil(0, True)
        time.sleep(1)

        # X0をOFFに
        print("X0 - OFF")
        client.write_coil(0, False)
        time.sleep(1)

finally:
    client.close()
