import yaml
import time
from datetime import datetime
import threading
import sys
import os
import re

from collections import deque
from modbus_server import ModbusBridge
from ladder_compiler import LadderCompiler

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
# 直感ラダー文字列 parser：旧正規表現版
# -----------------------------
def parse_ladder_line_old(line):
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

    # m = re.match(r"\[(.+)\]\s*--\((\w+)\)", line)
    # if m:
    #     logic_str, coil = m.groups()
    #     return {"logic": logic_str.strip(), "coil": coil.strip()}

    m = re.match(r"\[(.+)\]\s*--\((.+)\)", line)
    if m:
        logic_str, coil = m.groups()
        # 万が一末尾に余計な文字("や))が残っていても除去する
        coil = coil.strip().replace(")","").replace('"', '')
        return {"logic": logic_str.strip(), "coil": coil}


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
def load_ladder_yaml(filename, compiler):
    with open(filename, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data.get("kind") != "ladder":
        raise ValueError("invalid ladder yaml")

    rungs = []
    for line in data.get("rungs", []):
        rung = compiler.compile_line(line)
        if rung:
            rungs.append(rung)
        else:
            # ラダーパースに失敗した行をコンソールに出力して気づけるようにする
            print(f"[ERROR] Failed to parse ladder line: {line}")
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
        self.mem.sys.heartbeat += 1
        self.mem.sys.scan_count += 1

        for idx, rung in enumerate(self.ladder):
            # 1. END命令の処理
            if rung.get("type") == "END":
                break

            # 2. 条件式の評価
            # Compilerが生成した "self.mem.X[10]" 等の文字列を eval
            logic_str = rung.get("logic")
            condition_met = eval(logic_str) if logic_str else True

            # 3. 複数出力の実行
            if "outputs" in rung:
                outputs = rung["outputs"]
                # 単一の辞書で届いた場合でもループ回るようにリスト化する
                if isinstance(outputs, dict):
                    outputs = [outputs]

                for out in outputs:
                    self.execute_output(out, condition_met, idx)

    def execute_output(self, out, en, rung_idx):
        out_type = out["type"]
        target = out.get("target") # "self.mem.Y[0]" などの文字列

        if out_type == "COIL":
            # 文字列を eval して現在の値を取得
            old_val = eval(target)
            new_val = bool(en)
            if old_val != new_val:
                exec(f"{target} = {new_val}")
                self.log(f"[LADDER] rung# {rung_idx}: {target} = {new_val}")

        # --- CALC命令 ---
        elif out_type == "CALC":
            if en:
                formula = out.get("formula")
                try:
                    # formulaは"self.mem.D[0] = self.mem.D[0] + 1"という文字列など
                    exec(formula)
                    # 毎スキャンログを出力すると膨大になるため、デバック時以外は出力を控えめに
                    # self.log(f"[CALC] {formula}")
                except Exception as e:
                    self.log(f"[ERROR] CALC failed: {formula} -> {e}")

        elif out_type == "TON":
            preset = out["preset"]
            # target("self.mem.T[1]") をそのままキーにして状態管理
            st = self.mem.T.setdefault(target, {"acc": 0, "on": False})

            prev_on = st["on"]
            if en:
                st["acc"] += (self.scan_cycle * 1000)
                if st["acc"] >= preset:
                    st["on"] = True
            else:
                st["acc"] = 0
                st["on"] = False
            
            # メモリ(self.mem.T[1])に状態を反映
            exec(f"{target} = {st['on']}")

            if prev_on != st["on"]:
                self.log(f"[TON] {target} turned {'ON' if st['on'] else 'OFF'} (acc={st['acc']})")

        elif out_type == "RES":
            if en:
                # 文字列の中に "T[" が含まれているかどうかでデバイス種別を判定
                if ".T[" in target:
                    self.mem.T[target] = {"acc": 0, "on": False}
                elif ".C[" in target:
                    self.mem.C[target] = {"count": 0, "prev": False, "done": False}
                
                # 物理メモリの値もFalse(0)にリセット
                exec(f"{target} = False")
                self.log(f"[RES] {target} reset")

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
        # デバッグ用：パース済みラダーの表示
        for idx, rung in enumerate(self.ladder):
            print(f"Parsed {idx}: {rung}")

        try:
            while self.power:
                self.scan()
                if time.time() - self.last_alive > 5:
                    self.log(f"PLC alive | hb={self.mem.sys.heartbeat} uptime={self.mem.sys.uptime_sec}s")
                    self.last_alive = time.time()
                time.sleep(self.scan_cycle)
        finally:
            self.log("PLC STOP")
            self.logger.close()

    # PLCの物理入力の模擬(devicesimからのXへの入力対応)
    def set_physical_input(self, addr: int, value: bool):
        """
        Modbus通信を介さず、物理的な配線からの入力を模倣して
        直接 X メモリを書き換える。
        """
        if 0 <= addr < len(self.mem.X):
            self.mem.X[addr] = value
            self.log(f"[PHYSICAL_INPUT] X{addr} set to {value}")

# -----------------------------
# 起動
# -----------------------------
def main():
    if len(sys.argv) != 3:
        print("Usage: python plcsim.py plc.yaml ladder.yaml")
        sys.exit(1)

    # 1. コンパイラを先に作成
    compiler = LadderCompiler()

    plc_conf = load_plc_yaml(sys.argv[1])
    ladder_conf = load_ladder_yaml(sys.argv[2], compiler)

    plc = PLC(plc_conf, ladder_conf)

    port = plc_conf["modbus"]["port"]
    plc.log(f"Starting Modbus server on port {port}")

    modbus = ModbusBridge(plc, port)
    threading.Thread(target=modbus.start, daemon=True).start()

    plc.run()


if __name__ == "__main__":
    main()
