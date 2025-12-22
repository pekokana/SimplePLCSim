import yaml
import time
from datetime import datetime
import threading
import sys
import os
import re
from modbus_server import ModbusBridge

# -----------------------------
# Logger
# -----------------------------
class Logger:
    def __init__(self, name, log_dir=None):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{ts}.log"

        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            self.path = os.path.join(log_dir, filename)
        else:
            self.path = filename

        self.fp = open(self.path, "a", encoding="utf-8")
        self.log(f"log file opened: {self.path}")

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
# メモリ
# -----------------------------
class Memory:
    def __init__(self, x, y, m, d):
        self.X = [False] * x
        self.Y = [False] * y
        self.M = [False] * m
        self.D = [0] * d
        self.T = {}
        self.C = {}


# -----------------------------
# 直感ラダー文字列 parser
# -----------------------------
def parse_ladder_line(line):
    line = line.strip()

    if line.startswith("END"):
        return {"type": "END"}

    # TON / TOF / CTU / RES（未実装）
    m = re.match(r"(TON|TOF|CTU|RES)\s+(.+)", line)
    if m:
        return {"type": m.group(1), "raw": line}

    # 通常ラダー
    m = re.match(r"\[(.+)\]\s*--\((\w+)\)", line)
    if m:
        logic_str, coil = m.groups()
        return {"logic": logic_str.strip(), "coil": coil.strip()}

    # 計算
    m = re.match(r"(D\d+)\s*=\s*(D\d+)\s*([\+\-\*/])\s*(D\d+)", line)
    if m:
        dest, src1, op, src2 = m.groups()
        typ_map = {'+': 'ADD', '-': 'SUB', '*': 'MUL', '/': 'DIV'}
        return {
            "type": typ_map[op],
            "dest": int(dest[1:]),
            "src1": int(src1[1:]),
            "src2": int(src2[1:])
        }

    # MOV
    m = re.match(r"(D\d+)\s*=\s*(D\d+)", line)
    if m:
        dest, src = m.groups()
        return {"type": "MOV", "dest": int(dest[1:]), "src": int(src[1:])}

    return None


# -----------------------------
# ladder.yaml 読み込み
# -----------------------------
def load_ladder_yaml(filename):
    with open(filename, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data.get("kind") != "ladder":
        raise ValueError("invalid ladder yaml: kind must be 'ladder'")

    if data.get("version") != "1.0":
        raise ValueError("unsupported ladder version")

    rungs = []
    for line in data.get("rungs", []):
        rung = parse_ladder_line(line)
        if rung:
            rungs.append(rung)

    return rungs


# -----------------------------
# plc.yaml 読み込み（NEW）
# -----------------------------
def load_plc_yaml(filename):
    with open(filename, encoding="utf-8") as f:
        plc_conf = yaml.safe_load(f)

    if plc_conf.get("kind") != "plc":
        raise ValueError("invalid plc yaml: kind must be 'plc'")

    if plc_conf.get("version") != "1.0":
        raise ValueError("unsupported plc version")

    return plc_conf


# -----------------------------
# PLC
# -----------------------------
class PLC:
    def __init__(self, plc_conf, ladder_conf):
        mem_conf = plc_conf["memory"]
        self.mem = Memory(
            mem_conf["X"],
            mem_conf["Y"],
            mem_conf["M"],
            mem_conf["D"]
        )

        self.ladder = ladder_conf
        self.scan_cycle = plc_conf["cpu"]["scan_cycle_ms"] / 1000
        self.power = plc_conf["power"]

        name = plc_conf.get("name", "plc")
        log_dir = plc_conf.get("log_dir")
        self.logger = Logger(f"plc_{name}", log_dir)
        self.log = self.logger.log

        self.log("PLC initialized")
        self.log(f"scan_cycle={self.scan_cycle}s")

        self.last_snapshot = None
        self.last_alive = time.time()

    def eval_logic(self, expr):
        expr = expr.replace("AND", "and").replace("OR", "or").replace("NOT", "not")
        for i in range(len(self.mem.X)):
            expr = expr.replace(f"X{i}", f"self.mem.X[{i}]")
        for i in range(len(self.mem.M)):
            expr = expr.replace(f"M{i}", f"self.mem.M[{i}]")
        return eval(expr)

    def scan(self):
        for idx, rung in enumerate(self.ladder):
            t = rung.get("type")

            if t == "END":
                self.log(f"SCAN END at rung {idx}")
                break

            if t:
                self.log(f"SCAN rung {idx}: type={t} (not implemented)")
                continue

            if "logic" in rung:
                res = self.eval_logic(rung["logic"])
                dev = rung["coil"][0]
                bit = int(rung["coil"][1:])
                getattr(self.mem, dev)[bit] = res

    def log_if_changed(self):
        snap = (
            tuple(self.mem.X),
            tuple(self.mem.M),
            tuple(self.mem.D),
            tuple(self.mem.Y)
        )
        if snap != self.last_snapshot:
            self.log(
                f"X={self.mem.X} | M={self.mem.M} | "
                f"D={self.mem.D} | Y={self.mem.Y}"
            )
            self.last_snapshot = snap

    def run(self):
        self.log("PLC START")
        try:
            while self.power:
                self.scan()
                self.log_if_changed()

                if time.time() - self.last_alive > 5:
                    self.log("PLC alive")
                    self.last_alive = time.time()

                time.sleep(self.scan_cycle)
        finally:
            self.log("PLC STOP")
            self.logger.close()


# -----------------------------
# 起動
# -----------------------------
def main():
    if len(sys.argv) != 3:
        print("Usage: python plc.py plc.yaml ladder.yaml")
        sys.exit(1)

    plc_conf_file = sys.argv[1]
    ladder_file = sys.argv[2]

    plc_conf = load_plc_yaml(plc_conf_file)
    ladder_conf = load_ladder_yaml(ladder_file)

    plc = PLC(plc_conf, ladder_conf)

    port = plc_conf["modbus"]["port"]
    plc.log(f"Starting Modbus server on port {port}")

    modbus = ModbusBridge(plc, port)
    threading.Thread(target=modbus.start, daemon=True).start()

    plc.run()


if __name__ == "__main__":
    main()
