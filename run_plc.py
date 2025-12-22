import yaml
import time
from datetime import datetime
import threading
import sys
import os
import re

from collections import deque

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
    # TON: TON T0 X0 2000 Y0
    m = re.match(r"TON\s+(T\d+)\s+(X\d+|M\d+)\s+(\d+)\s+(Y\d+|M\d+)", line)
    if m:
        timer, enable, preset, out = m.groups()
        return {
            "type": "TON",
            "timer": timer,
            "enable": enable,
            "preset": int(preset),
            "out": out
        }

    # CTU: CTU C0 X1 5 M0
    m = re.match(r"CTU\s+(C\d+)\s+(X\d+|M\d+)\s+(\d+)\s+(Y\d+|M\d+)", line)
    if m:
        counter, inp, preset, out = m.groups()
        return {
            "type": "CTU",
            "counter": counter,
            "input": inp,
            "preset": int(preset),
            "out": out
        }

    # TOF: TOF T1 X2 3000 Y1
    m = re.match(r"TOF\s+(T\d+)\s+(X\d+|M\d+)\s+(\d+)\s+(Y\d+|M\d+)", line)
    if m:
        timer, enable, preset, out = m.groups()
        return {
            "type": "TOF",
            "timer": timer,
            "enable": enable,
            "preset": int(preset),
            "out": out
        }

    # RES: RES C0   /  RES T0
    m = re.match(r"RES\s+([TC]\d+)", line)
    if m:
        target = m.group(1)
        return {
            "type": "RES",
            "target": target
        }

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

        self.event_queue = deque(maxlen=1000)
        self.prev_snapshot = {
            "X": list(self.mem.X),
            "Y": list(self.mem.Y),
            "M": list(self.mem.M),
            "D": list(self.mem.D),
        }

    def eval_logic(self, expr):
        expr = expr.replace("AND", "and").replace("OR", "or").replace("NOT", "not")
        for i in range(len(self.mem.X)):
            expr = expr.replace(f"X{i}", f"self.mem.X[{i}]")
        for i in range(len(self.mem.M)):
            expr = expr.replace(f"M{i}", f"self.mem.M[{i}]")
        return eval(expr)

    def get_bit(self, name):
        dev = name[0]
        idx = int(name[1:])
        return getattr(self.mem, dev)[idx]

    def set_bit(self, name, value):
        dev = name[0]
        idx = int(name[1:])
        getattr(self.mem, dev)[idx] = value

    def scan(self):
        for idx, rung in enumerate(self.ladder):
            t = rung.get("type")

            if t == "END":
                self.log(f"SCAN END at rung {idx}")
                break

            if t == "TON":
                tid = rung["timer"]
                enable = self.get_bit(rung["enable"])
                preset = rung["preset"]
                out = rung["out"]

                timer = self.mem.T.setdefault(tid, {
                    "start": None,
                    "done": False
                })

                if enable:
                    if timer["start"] is None:
                        timer["start"] = time.time()
                    elif not timer["done"]:
                        if (time.time() - timer["start"]) * 1000 >= preset:
                            timer["done"] = True
                else:
                    timer["start"] = None
                    timer["done"] = False

                self.set_bit(out, timer["done"])
                continue

            if t == "CTU":
                cid = rung["counter"]
                inp = self.get_bit(rung["input"])
                preset = rung["preset"]
                out = rung["out"]

                counter = self.mem.C.setdefault(cid, {
                    "count": 0,
                    "prev": False,
                    "done": False
                })

                if inp and not counter["prev"]:
                    counter["count"] += 1
                    if counter["count"] >= preset:
                        counter["done"] = True

                counter["prev"] = inp
                self.set_bit(out, counter["done"])
                continue

            if t == "TOF":
                tid = rung["timer"]
                enable = self.get_bit(rung["enable"])
                preset = rung["preset"]
                out = rung["out"]

                timer = self.mem.T.setdefault(tid, {
                    "start": None,
                    "done": False,
                    "prev_enable": False
                })

                if enable:
                    timer["done"] = True
                    timer["start"] = None
                else:
                    if timer["prev_enable"]:
                        timer["start"] = time.time()
                    if timer["start"] is not None:
                        if (time.time() - timer["start"]) * 1000 >= preset:
                            timer["done"] = False

                timer["prev_enable"] = enable
                self.set_bit(out, timer["done"])
                continue

            if t == "RES":
                target = rung["target"]

                if target.startswith("T"):
                    if target in self.mem.T:
                        self.mem.T[target] = {
                            "start": None,
                            "done": False,
                            "prev_enable": False
                        }

                if target.startswith("C"):
                    if target in self.mem.C:
                        self.mem.C[target] = {
                            "count": 0,
                            "prev": False,
                            "done": False
                        }

                continue

            if t:
                self.log(f"SCAN rung {idx}: type={t} (not implemented)")
                continue

            if "logic" in rung:
                res = self.eval_logic(rung["logic"])
                dev = rung["coil"][0]
                bit = int(rung["coil"][1:])
                getattr(self.mem, dev)[bit] = res

    def detect_events(self):
        # Y変化 → 出力イベント
        for i, (b, a) in enumerate(zip(self.prev_snapshot["Y"], self.mem.Y)):
            if b != a:
                self.raise_event("OUTPUT_CHANGE", f"Y{i}", b, a)

        # M変化 → 内部イベント
        for i, (b, a) in enumerate(zip(self.prev_snapshot["M"], self.mem.M)):
            if b != a:
                self.raise_event("INTERNAL_CHANGE", f"M{i}", b, a)

        # スナップショット更新
        self.prev_snapshot["X"] = list(self.mem.X)
        self.prev_snapshot["Y"] = list(self.mem.Y)
        self.prev_snapshot["M"] = list(self.mem.M)
        self.prev_snapshot["D"] = list(self.mem.D)

    def log_if_changed(self):
        snap = (
            tuple(self.mem.X),
            tuple(self.mem.M),
            tuple(self.mem.D),
            tuple(self.mem.Y),
            tuple((k, v.get("done"), v.get("count", None)) for k, v in self.mem.C.items()),
            tuple((k, v.get("done")) for k, v in self.mem.T.items())
        )

        if snap != self.last_snapshot:
            self.log(
                f"X={self.mem.X} | M={self.mem.M} | "
                f"D={self.mem.D} | Y={self.mem.Y} | "
                f"T={self.mem.T} | C={self.mem.C}"
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
