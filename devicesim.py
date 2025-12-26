import yaml
import sys
import time
import os
from datetime import datetime
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException

SUPPORTED_DEVICE_VERSIONS = {"1.0"}

# -----------------------------
# Logger
# -----------------------------
class Logger:
    def __init__(self, device_name, log_dir=None):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{device_name}_{timestamp}.log"

        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            self.log_path = os.path.join(log_dir, filename)
        else:
            self.log_path = filename

        self.fp = open(self.log_path, "a", encoding="utf-8")
        self.log(f"log file opened: {self.log_path}")

    def log(self, msg):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{now} | {msg}"
        print(line, flush=True)
        if self.fp:
            self.fp.write(line + "\n")
            self.fp.flush()
            os.fsync(self.fp.fileno())

    def close(self):
        self.log("log file closed")
        self.fp.close()

# -----------------------------
# device.yaml loader
# -----------------------------
def load_device_yaml(filename):
    with open(filename, encoding="utf-8") as f:
        conf = yaml.safe_load(f)

    if conf.get("kind") != "device":
        raise ValueError("invalid device yaml: kind must be 'device'")

    version = str(conf.get("version"))
    if version not in SUPPORTED_DEVICE_VERSIONS:
        raise ValueError(f"unsupported device version: {version}")

    if "device" not in conf:
        raise ValueError("device section not found in yaml")

    return conf["device"]

# -----------------------------
# Device Simulator
# -----------------------------
class DeviceSimulator:
    MAX_PLC_ERRORS = 3
    RECONNECT_WAIT = 1.0

    # heartbeat 監視設定
    HEARTBEAT_ADDR = 10000
    HEARTBEAT_TIMEOUT = 3.0   # 秒（変化しなければ NG）

    def __init__(self, yaml_file):
        device = load_device_yaml(yaml_file)

        self.name = device["name"]
        self.signals = device["signals"]
        self.cycle = device.get("cycle_ms", 100) / 1000
        self.log_dir = device.get("log_dir")

        plc = device["plc"]
        self.plc_host = plc["host"]
        self.plc_port = plc["port"]

        self.logger = Logger(self.name, self.log_dir)
        self.log = self.logger.log

        self.log(f"loading config: {yaml_file}")
        self.log(f"signals={list(self.signals.keys())}")

        self.client = None
        self.plc_error_count = 0

        # heartbeat 状態
        self.last_heartbeat = None
        self.last_hb_change = time.time()

        self.connect_plc()

        self.log(f"[Device:{self.name}] cycle={self.cycle}s")
        self.last_alive = time.time()

    # -----------------------------
    # PLC Connection
    # -----------------------------
    def connect_plc(self):
        self.log(f"[Device:{self.name}] connecting to PLC {self.plc_host}:{self.plc_port}")
        self.client = ModbusTcpClient(self.plc_host, port=self.plc_port, timeout=2)

        if not self.client.connect():
            raise RuntimeError("initial PLC connection failed")

        self.log(f"[Device:{self.name}] PLC connected")

        # heartbeat 初期化
        self.last_heartbeat = None
        self.last_hb_change = time.time()

    def handle_plc_error(self, e):
        self.plc_error_count += 1
        self.log(
            f"[Device:{self.name}][WARN] PLC communication error "
            f"({self.plc_error_count}/{self.MAX_PLC_ERRORS}): {e}"
        )

        try:
            self.client.close()
        except Exception:
            pass

        if self.plc_error_count >= self.MAX_PLC_ERRORS:
            self.log(f"[Device:{self.name}][FATAL] PLC lost (communication).")
            self.shutdown()
            sys.exit(1)

        time.sleep(self.RECONNECT_WAIT)
        self.connect_plc()

    # -----------------------------
    # PLC heartbeat check
    # -----------------------------
    def check_heartbeat(self):
        try:
            # address=10000 は PLC側の HR_SYS_BASE + 0 と一致させる
            rr = self.client.read_holding_registers(
                address=self.HEARTBEAT_ADDR,
                count=1,
                slave=1
            )

            if not rr or rr.isError():
                # 起動直後はPLC側の準備ができていないことが多いため、WARNログに留めて return する
                self.log(f"[Device:{self.name}][DEBUG] Heartbeat read failed (PLC not ready?)")
                return 

            hb = rr.registers[0]

            if self.last_heartbeat is None:
                self.last_heartbeat = hb
                self.last_hb_change = time.time()
                return

            if hb != self.last_heartbeat:
                self.last_heartbeat = hb
                self.last_hb_change = time.time()
                return

            if time.time() - self.last_hb_change > self.HEARTBEAT_TIMEOUT:
                self.log(f"[Device:{self.name}][FATAL] PLC heartbeat stopped (>{self.HEARTBEAT_TIMEOUT}s)")
                self.shutdown()
                sys.exit(1)
        except Exception as e:
            # 接続エラーなどは上位の handle_plc_error で処理されるため、ここではログのみ
            self.log(f"[Device:{self.name}][DEBUG] Heartbeat exception: {e}")

    # -----------------------------
    # Main Loop
    # -----------------------------
    def run(self):
        self.log(f"[Device:{self.name}] START")
        try:
            while True:
                try:
                    # 接続確認（切れていたら再接続）
                    if not self.client.is_socket_open():
                        self.connect_plc()

                    # heartbeat 監視 (失敗しても即終了しないように内部で制御)
                    self.check_heartbeat()

                    for name, sig in self.signals.items():
                        self.process_signal(name, sig)

                    self.plc_error_count = 0

                except (ModbusIOException, OSError, ConnectionError) as e:
                    self.handle_plc_error(e)
                except Exception as e:
                    self.log(f"[Device:{self.name}][ERROR] Unexpected error: {e}")

                if time.time() - self.last_alive >= 5:
                    self.log(f"[Device:{self.name}] alive")
                    self.last_alive = time.time()

                time.sleep(self.cycle)
        finally:
            self.shutdown()

    def shutdown(self):
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass

        self.log(f"[Device:{self.name}] STOP")
        self.logger.close()

    # -----------------------------
    # Signal Processing
    # -----------------------------
    def process_signal(self, name, sig):
        typ = sig["type"]

        if typ == "coil":
            self.run_pattern(name, sig, coil=True)
        elif typ == "register":
            self.run_pattern(name, sig, register=True)
        elif typ == "pulse":
            self.run_pulse(name, sig)
        else:
            raise ValueError(f"unknown signal type: {typ}")

    def run_pattern(self, name, sig, coil=False, register=False):
        if "_idx" not in sig:
            sig["_idx"] = 0
            sig["_next"] = time.time()
            sig["_last"] = None

        if time.time() >= sig["_next"]:
            step = sig["pattern"][sig["_idx"]]
            addr = sig["address"]
            value = step["value"]

            if sig["_last"] != value:
                if coil:
                    self.client.write_coil(addr, value)
                    self.log(f"[{self.name}] {name} -> X{addr} = {value}")
                elif register:
                    self.client.write_register(addr, value)
                    self.log(f"[{self.name}] {name} -> D{addr} = {value}")

                sig["_last"] = value

            sig["_next"] = time.time() + step["duration_ms"] / 1000
            sig["_idx"] = (sig["_idx"] + 1) % len(sig["pattern"])

    def run_pulse(self, name, sig):
        if "_next" not in sig:
            sig["_next"] = time.time()

        if time.time() >= sig["_next"]:
            addr = sig["address"]

            self.log(f"[{self.name}] {name} pulse -> X{addr} ON")
            self.client.write_coil(addr, True)

            time.sleep(sig["pulse_ms"] / 1000)

            self.client.write_coil(addr, False)
            self.log(f"[{self.name}] {name} pulse -> X{addr} OFF")

            sig["_next"] = time.time() + sig["interval_ms"] / 1000

# -----------------------------
# 起動
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python device_simulator.py device_conf/xxx.yaml")
        sys.exit(1)

    DeviceSimulator(sys.argv[1]).run()
