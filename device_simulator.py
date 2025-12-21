import yaml
import sys
import time
import os
from datetime import datetime
from pymodbus.client import ModbusTcpClient

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
        self.fp.write(line + "\n")
        self.fp.flush()

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
    def __init__(self, yaml_file):
        device = load_device_yaml(yaml_file)

        self.name = device["name"]
        self.signals = device["signals"]
        self.cycle = device.get("cycle_ms", 100) / 1000
        self.log_dir = device.get("log_dir")

        plc = device["plc"]

        # logger
        self.logger = Logger(self.name, self.log_dir)
        self.log = self.logger.log

        self.log(f"loading config: {yaml_file}")
        self.log(f"signals={list(self.signals.keys())}")

        self.client = ModbusTcpClient(plc["host"], port=plc["port"])
        self.client.connect()

        self.log(f"[Device:{self.name}] connected to PLC {plc['host']}:{plc['port']}")
        self.log(f"[Device:{self.name}] cycle={self.cycle}s")

        self.last_alive = time.time()

    def run(self):
        self.log(f"[Device:{self.name}] START")
        try:
            while True:
                for name, sig in self.signals.items():
                    self.process_signal(name, sig)

                if time.time() - self.last_alive >= 5:
                    self.log(f"[Device:{self.name}] alive")
                    self.last_alive = time.time()

                time.sleep(self.cycle)
        finally:
            self.client.close()
            self.log(f"[Device:{self.name}] STOP")
            self.logger.close()

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
