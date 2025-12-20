import yaml
import time
from datetime import datetime
import threading
import sys
from modbus_server import ModbusBridge
import re

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
# ラダー parser
# -----------------------------
def parse_ladder_line(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    if line.upper() == "END":
        return {"type": "END"}

    m = re.match(r"\[(.*?)\]\s*--\((.*?)\)", line)
    if not m:
        raise ValueError(f"不正なラダー記述: {line}")

    inside, out = m.groups()
    tokens = inside.strip().split()

    if tokens[0].upper() == "TON":
        if len(tokens) != 4:
            raise ValueError(f"TONの引数が不正: {line}")
        return {
            "type": "TON",
            "timer": tokens[1],
            "enable": tokens[2],
            "preset": int(tokens[3]),
            "out": out
        }

    elif tokens[0].upper() == "CTU":
        if len(tokens) != 4:
            raise ValueError(f"CTUの引数が不正: {line}")
        return {
            "type": "CTU",
            "counter": tokens[1],
            "input": tokens[2],
            "preset": int(tokens[3]),
            "out": out
        }

    else:
        logic_expr = " ".join(tokens)
        return {
            "logic": logic_expr,
            "coil": out
        }

def ladder_text_to_yaml(lines):
    ladder_conf = []
    for line in lines:
        parsed = parse_ladder_line(line)
        if parsed:
            ladder_conf.append(parsed)
    return ladder_conf

# -----------------------------
# ラダー評価
# -----------------------------
def eval_logic(expr, mem):
    expr = expr.replace("AND", "and").replace("OR", "or").replace("NOT", "not")
    for i in range(len(mem.X)):
        expr = expr.replace(f"X{i}", f"mem.X[{i}]")
    for i in range(len(mem.M)):
        expr = expr.replace(f"M{i}", f"mem.M[{i}]")
    return eval(expr)

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
            mem_conf["D"],
        )
        self.ladder = ladder_conf
        self.scan_cycle = plc_conf["cpu"]["scan_cycle_ms"] / 1000
        self.power = plc_conf["power"]

        # カウンタ内部状態
        self.C = {}
        self.prev_inputs = {}

    def scan(self):
        for rung in self.ladder:
            rtype = rung.get("type")

            if rtype == "TON":
                self.exec_ton(rung)
            elif rtype == "CTU":
                self.exec_ctu(rung)
            elif rtype == "END":
                continue
            elif "logic" in rung and "coil" in rung:
                result = eval_logic(rung["logic"], self.mem)
                dev = rung["coil"][0]
                idx = int(rung["coil"][1:])
                getattr(self.mem, dev)[idx] = result

    def run(self):
        print("PLC START")
        while self.power:
            self.scan()
            self.print_status()
            time.sleep(self.scan_cycle)

    def print_status(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"{now} | X={self.mem.X} | M={self.mem.M} | Y={self.mem.Y}")

    def exec_ton(self, rung):
        name = rung["timer"]
        if name not in self.mem.T:
            self.mem.T[name] = Timer(rung["preset"])

        timer = self.mem.T[name]
        dev = rung["enable"][0]
        idx = int(rung["enable"][1:])
        enable = getattr(self.mem, dev)[idx]
        timer.update(enable)

        odev = rung["out"][0]
        oidx = int(rung["out"][1:])
        getattr(self.mem, odev)[oidx] = timer.done

    def exec_ctu(self, rung):
        cname = rung["counter"]
        inp = rung["input"]
        preset = rung["preset"]
        out = rung["out"]

        if cname not in self.C:
            self.C[cname] = 0
            self.prev_inputs[inp] = False

        dev = inp[0]
        idx = int(inp[1:])
        current = getattr(self.mem, dev)[idx]

        if current and not self.prev_inputs[inp]:
            self.C[cname] += 1
            print(f"[CTU] {cname} = {self.C[cname]}")

        self.prev_inputs[inp] = current

        if self.C[cname] >= preset:
            odev = out[0]
            oidx = int(out[1:])
            getattr(self.mem, odev)[oidx] = True

# -----------------------------
# Timer
# -----------------------------
class Timer:
    def __init__(self, preset):
        self.preset = preset
        self.start = None
        self.done = False

    def update(self, enable):
        if enable:
            if self.start is None:
                self.start = time.time()
            self.done = (time.time() - self.start) * 1000 >= self.preset
        else:
            self.start = None
            self.done = False

# -----------------------------
# 起動
# -----------------------------
def main():
    plc_conf_file = sys.argv[1]
    ladder_conf_file = sys.argv[2]

    # ladder.yaml を直感文字列で読み込む場合
    with open(ladder_conf_file, encoding="utf-8") as f:
        ladder_lines = f.readlines()
    ladder_conf = ladder_text_to_yaml(ladder_lines)

    with open(plc_conf_file, encoding="utf-8") as f:
        plc_conf = yaml.safe_load(f)

    plc = PLC(plc_conf, ladder_conf)

    # Modbus起動
    port = plc_conf["modbus"]["port"]
    modbus = ModbusBridge(plc, port)
    threading.Thread(target=modbus.start, daemon=True).start()

    plc.run()

if __name__ == "__main__":
    main()
