import yaml
import time
import sys
import os
import argparse
from datetime import datetime
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException

SUPPORTED_IODEVICE_VERSIONS = {"1.0"}

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
        if hasattr(self, 'fp') and not self.fp.closed:
            self.fp.write(line + "\n")
            self.fp.flush()
            os.fsync(self.fp.fileno())

    def close(self):
        if hasattr(self, 'fp') and not self.fp.closed:
            self.log("log file closed")
            self.fp.close()

# -----------------------------
# IODevice
# -----------------------------
class IODevice:
    HB_ADDR = 10000
    HB_TIMEOUT = 5.0  # 秒
    RECONNECT_WAIT = 1.0 # 再接続を試みるまでの待機時間（秒）

    def __init__(self, yaml_file):
        self.config = self.load_config(yaml_file)
        
        self.name = self.config.get('name', 'iodevice_bridge')
        self.connections = self.config.get('connections', [])
        self.cycle = self.config.get('cycle_ms', 200) / 1000.0
        self.log_dir = self.config.get('log_dir')

        self.logger = Logger(self.name, self.log_dir)
        self.log = self.logger.log

        self.clients = {}
        self.last_attempt = {} # 各ホストごとの最終接続試行時刻
        self.hb_states = {}  # 各接続先のハートビート状態
        self.last_alive = time.time()
        self.log(f"loading config: {yaml_file}")

    def load_config(self, filename):
        with open(filename, 'r', encoding='utf-8') as f:
            conf = yaml.safe_load(f)

        if conf.get("kind") != "iodevice":
            raise ValueError("invalid iodevice yaml: kind must be 'iodevice'")

        version = str(conf.get("version"))
        if version not in SUPPORTED_IODEVICE_VERSIONS:
            raise ValueError(f"unsupported iodevice version: {version}")

        return conf

    def get_client(self, host, port):
        key = f"{host}:{port}"
        if key not in self.clients:
            self.clients[key] = ModbusTcpClient(host, port=port, timeout=2)
            self.last_attempt[key] = 0
        
        client = self.clients[key]
        if not client.connected:
            now = time.time()
            # 前回の試行から RECONNECT_WAIT 秒経過していなければスキップ
            if now - self.last_attempt[key] < self.RECONNECT_WAIT:
                return None
            
            self.last_attempt[key] = now
            if not client.connect():
                # ログの氾濫を防ぐため DEBUG 扱いにするか、限定的に出す
                return None
            else:
                self.log(f"[INFO] Connected to {key}")
        return client

    def check_heartbeat(self, host, port):
        key = f"{host}:{port}"
        client = self.get_client(host, port)
        if not client or not client.connected:
            return

        try:
            rr = client.read_holding_registers(self.HB_ADDR, 1, slave=1)
            if rr is None or rr.isError():
                return 

            hb_val = rr.registers[0]
            now = time.time()

            if key not in self.hb_states:
                self.hb_states[key] = {'val': hb_val, 'time': now}
                return

            if hb_val != self.hb_states[key]['val']:
                self.hb_states[key] = {'val': hb_val, 'time': now}
            else:
                if now - self.hb_states[key]['time'] > self.HB_TIMEOUT:
                    self.log(f"[FATAL] PLC {key} heartbeat stopped (>{self.HB_TIMEOUT}s)")
                    self.shutdown()
                    sys.exit(1)
        except Exception as e:
            self.log(f"[DEBUG] HB check error {key}: {e}")

    def read_value(self, node):
        client = self.get_client(node['host'], node['port'])
        if not client: return None
        
        addr = node['address']
        try:
            if node['type'] == 'coil':
                res = client.read_coils(addr, 1, slave=1)
                return res.bits[0] if not res.isError() else None
            elif node['type'] == 'hr':
                res = client.read_holding_registers(addr, 1, slave=1)
                return res.registers[0] if not res.isError() else None
        except Exception as e:
            # 通信エラーは頻出するため、接続が切れた場合は get_client 側で再接続を促す
            pass
        return None

    def write_value(self, node, value):
        client = self.get_client(node['host'], node['port'])
        if not client: return
        
        addr = node['address']
        try:
            if node['type'] == 'coil':
                client.write_coil(addr, value, slave=1)
            elif node['type'] == 'hr':
                client.write_register(addr, int(value), slave=1)
        except Exception as e:
            pass

    def execute_action(self, action, rule_name):
        current = self.read_value(action)
        if current is None: return
        
        op = action.get('op')
        val = action.get('value', 1)
        
        new_val = current
        if op == 'increment': new_val = current + val
        elif op == 'decrement': new_val = max(0, current - val)
        elif op == 'add': new_val = current + val
        elif op == 'set': new_val = val
        else: return
        
        if new_val != current:
            self.write_value(action, new_val)
            self.log(f"[ACTION] {rule_name}: {action['host']}:{action['address']} {op}({val}) {current}->{new_val}")

    def run(self):
        self.log(f"[*] START ({len(self.connections)} rules, cycle={self.cycle}s)")
        last_states = {}

        try:
            while True:
                try:
                    # 1. ハートビート監視
                    targets = set()
                    for conn in self.connections:
                        for key in ['trigger', 'source', 'target']:
                            node = conn.get(key)
                            if node: targets.add((node['host'], node['port']))
                    
                    for h, p in targets:
                        self.check_heartbeat(h, p)

                    # 2. 転送ルール処理
                    for i, conn in enumerate(self.connections):
                        rule_name = conn.get('name', f"rule_{i}")
                        trigger_node = conn.get('trigger') or conn.get('source')
                        current_val = self.read_value(trigger_node)
                        
                        if current_val is None: continue
                        prev_val = last_states.get(rule_name, False)

                        if current_val and not prev_val:
                            self.log(f"[EVENT] Triggered: {rule_name}")
                            if 'target' in conn:
                                self.write_value(conn['target'], True)
                            for action in conn.get('actions', []):
                                self.execute_action(action, rule_name)
                        
                        elif not current_val and prev_val:
                            if 'target' in conn:
                                self.write_value(conn['target'], False)

                        last_states[rule_name] = current_val

                except Exception as e:
                    self.log(f"[ERROR] Loop error: {e}")

                if time.time() - self.last_alive >= 5:
                    self.log(f"[*] alive")
                    self.last_alive = time.time()

                time.sleep(self.cycle)

        except KeyboardInterrupt:
            self.log("[*] Interrupted by user")
        finally:
            self.shutdown()

    def shutdown(self):
        for key, client in self.clients.items():
            try:
                client.close()
                self.log(f"[*] Closed connection to {key}")
            except: pass
        self.log("[*] STOP")
        self.logger.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python iodevice.py device_conf/iodevice.yaml")
        sys.exit(1)
    
    try:
        IODevice(sys.argv[1]).run()
    except Exception as e:
        print(f"Fatal error: {e}")