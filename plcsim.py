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
# システムメモリ（ladder 非公開）
# -----------------------------
class SystemMemory:
    def __init__(self):
        self.heartbeat = 0
        self.scan_count = 0
        self.start_time = time.time()

    @property
    def uptime_sec(self):
        return int(time.time() - self.start_time)


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

        self.sys = SystemMemory()


# -----------------------------
# 直感ラダー文字列 parser
# -----------------------------
def parse_ladder_line(line):
    line = line.strip()

    if line.startswith("END"):
        return {"type": "END"}

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

    m = re.match(r"RES\s+([TC]\d+)", line)
    if m:
        return {"type": "RES", "target": m.group(1)}

    m = re.match(r"\[(.+)\]\s*--\((\w+)\)", line)
    if m:
        logic_str, coil = m.groups()
        return {"logic": logic_str.strip(), "coil": coil.strip()}

    m = re.match(r"(D\d+)\s*=\s*(D\d+)\s*([\+\-\*/])\s*(D\d+)", line)
    if m:
        dest, src1, op, src2 = m.groups()
        return {
            "type": {'+': 'ADD', '-': 'SUB', '*': 'MUL', '/': 'DIV'}[op],
            "dest": int(dest[1:]),
            "src1": int(src1[1:]),
            "src2": int(src2[1:])
        }

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
        raise ValueError("invalid ladder yaml")

    rungs = []
    for line in data.get("rungs", []):
        rung = parse_ladder_line(line)
        if rung:
            rungs.append(rung)
    return rungs


# -----------------------------
# plc.yaml 読み込み
# -----------------------------
def load_plc_yaml(filename):
    with open(filename, encoding="utf-8") as f:
        plc_conf = yaml.safe_load(f)

    if plc_conf.get("kind") != "plc":
        raise ValueError("invalid plc yaml")

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
        self.logger = Logger(f"plc_{name}", plc_conf.get("log_dir"))
        self.log = self.logger.log

        self.log("PLC initialized")
        self.log(f"scan_cycle={self.scan_cycle}s")

        self.last_snapshot = None
        self.last_alive = time.time()

    def scan(self):
        # system heartbeat 更新
        self.mem.sys.heartbeat += 1
        self.mem.sys.scan_count += 1

        for idx, rung in enumerate(self.ladder):
            t = rung.get("type")

            if t == "END":
                self.log(f"SCAN END at rung {idx}")
                break

            if t == "TON":
                timer = rung["timer"]
                enable = self.get_bit(rung["enable"])
                preset = rung["preset"]
                out_dev = rung["out"][0]
                out_bit = int(rung["out"][1:])

                st = self.mem.T.setdefault(
                    timer,
                    {"acc": 0, "on": False}
                )

                if enable:
                    st["acc"] += 1
                    if st["acc"] >= preset:
                        st["on"] = True
                else:
                    st["acc"] = 0
                    st["on"] = False

                prev = getattr(self.mem, out_dev)[out_bit]
                getattr(self.mem, out_dev)[out_bit] = st["on"]

                if prev != st["on"]:
                    self.log(
                        f"[TON] {timer} acc={st['acc']} preset={preset} -> {rung['out']}={st['on']}"
                    )

                continue

            if t == "CTU":
                counter = rung["counter"]
                inp = self.get_bit(rung["input"])
                preset = rung["preset"]
                out = rung["out"]

                st = self.mem.C.setdefault(
                    counter,
                    {"count": 0, "prev": False, "done": False}
                )

                if inp and not st["prev"]:
                    st["count"] += 1
                    if st["count"] >= preset:
                        st["done"] = True

                st["prev"] = inp

                prev = self.get_bit(out)
                self.set_bit(out, st["done"])

                if prev != st["done"]:
                    self.log(
                        f"[CTU] {counter} count={st['count']} preset={preset} -> {out}={st['done']}"
                    )

                continue


            if t == "TOF":
                timer = rung["timer"]
                enable = self.get_bit(rung["enable"])
                preset = rung["preset"]
                out_dev = rung["out"][0]
                out_bit = int(rung["out"][1:])

                st = self.mem.T.setdefault(
                    timer,
                    {"acc": 0, "on": False}
                )

                if enable:
                    st["on"] = True
                    st["acc"] = preset
                else:
                    if st["acc"] > 0:
                        st["acc"] -= 1
                    else:
                        st["on"] = False

                prev = getattr(self.mem, out_dev)[out_bit]
                getattr(self.mem, out_dev)[out_bit] = st["on"]

                if prev != st["on"]:
                    self.log(
                        f"[TOF] {timer} acc={st['acc']} preset={preset} -> {rung['out']}={st['on']}"
                    )

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
                        self.log(f"[RES] Timer {target} reset")

                elif target.startswith("C"):
                    if target in self.mem.C:
                        self.mem.C[target] = {
                            "count": 0,
                            "prev": False,
                            "done": False
                        }
                        self.log(f"[RES] Counter {target} reset")

                continue


            # 未実装検知
            if t:
                self.log(f"SCAN rung {idx}: type={t} (not implemented)")
                continue

            if "logic" in rung:
                res = self.eval_logic(rung["logic"])
                dev = rung["coil"][0]
                bit = int(rung["coil"][1:])

                old = getattr(self.mem, dev)[bit]
                getattr(self.mem, dev)[bit] = res

                if old != res:
                    self.log(
                        f"[LADDER] rung# {idx} "
                        f"{rung['logic']} -> {rung['coil']} = {res}"
                    )

    def get_bit(self, addr):
        dev = addr[0]
        bit = int(addr[1:])
        return getattr(self.mem, dev)[bit]

    def set_bit(self, name: str, value: bool):
        """X/M/Y のビットを設定"""
        dev = name[0]
        idx = int(name[1:])
        getattr(self.mem, dev)[idx] = value

    def eval_logic(self, expr):
        expr = expr.replace("AND", "and").replace("OR", "or").replace("NOT", "not")
        for i in range(len(self.mem.X)):
            expr = expr.replace(f"X{i}", f"self.mem.X[{i}]")
        for i in range(len(self.mem.M)):
            expr = expr.replace(f"M{i}", f"self.mem.M[{i}]")
        return eval(expr)

    def run(self):
        self.log("PLC START")
        try:
            while self.power:
                self.scan()

                if time.time() - self.last_alive > 5:
                    self.log(
                        f"PLC alive | hb={self.mem.sys.heartbeat} "
                        f"uptime={self.mem.sys.uptime_sec}s"
                    )
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
        print("Usage: python plcsim.py plc.yaml ladder.yaml")
        sys.exit(1)

    plc_conf = load_plc_yaml(sys.argv[1])
    ladder_conf = load_ladder_yaml(sys.argv[2])

    plc = PLC(plc_conf, ladder_conf)

    port = plc_conf["modbus"]["port"]
    plc.log(f"Starting Modbus server on port {port}")

    modbus = ModbusBridge(plc, port)
    threading.Thread(target=modbus.start, daemon=True).start()

    plc.run()


if __name__ == "__main__":
    main()
