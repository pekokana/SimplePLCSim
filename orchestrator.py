import yaml
import subprocess
import sys
import time
import threading
from datetime import datetime
import os
import glob

from pymodbus.client import ModbusTcpClient

PYTHON = sys.executable

# -------------------------------------------------
# Default logger (will be overridden)
# -------------------------------------------------
def log(msg):
    print(msg)

# -----------------------------
# Orchestrator Logger
# -----------------------------
class OrchestratorLogger:
    def __init__(self, log_file):
        self.log_file = log_file

    def log(self, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{ts} | {msg}"
        #print(line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

# -----------------------------
# Global State & Locks
# -----------------------------
running = True
processes = {}        # name -> Popen
svc_ready_status = {}  # name -> bool
svc_map = {}
rev_deps = {}
log_func = None
state_lock = threading.Lock() # スレッド安全のためのロック
disabled_services = set()

# -----------------------------
# YAML Loader
# -----------------------------
def load_orchestrator_yaml(path):
    with open(path, encoding="utf-8") as f:
        conf = yaml.safe_load(f)

    if conf.get("kind") != "orchestrator":
        raise ValueError("invalid kind (must be orchestrator)")
    if conf.get("version") != "1.0":
        raise ValueError("unsupported orchestrator version")

    return conf

# -----------------------------
# Dependency Resolve
# -----------------------------
def resolve_start_order(services):
    svc_map = {svc["name"]: svc for svc in services}
    resolved = []
    visited = set()

    def visit(name, stack):
        if name in visited:
            return
        if name in stack:
            raise ValueError(f"cyclic dependency detected: {name}")

        stack.add(name)
        svc = svc_map[name]

        for dep in svc.get("depends_on", []):
            if dep not in svc_map:
                raise ValueError(f"unknown dependency: {dep}")
            visit(dep, stack)

        stack.remove(name)
        visited.add(name)
        resolved.append(svc)

    for svc in services:
        visit(svc["name"], set())

    return resolved

# -----------------------------
# Ready Check
# -----------------------------
def wait_modbus_ready(host, port, timeout):
    start = time.time()
    success = 0

    while time.time() - start < timeout:
        try:
            client = ModbusTcpClient(host, port=port, timeout=2)
            if client.connect():
                client.close()
                success += 1
                if success >= 2:
                    return True
        except Exception:
            success = 0

        time.sleep(0.5)

    return False


def wait_service_ready(svc):
    rc = svc.get("ready_check")
    if not rc:
        return True

    kind = rc.get("kind")
    timeout = rc.get("timeout_sec", 10)

    if kind == "modbus":
        host = rc["host"]
        port = rc["port"]

        log(f"[orchestrator] waiting for {svc['name']} modbus ready {host}:{port}")
        if wait_modbus_ready(host, port, timeout):
            log(f"[orchestrator] {svc['name']} READY")
            return True

        log(f"[orchestrator][WARN] {svc['name']} not ready yet")
        return False

    raise ValueError(f"unsupported ready_check kind: {kind}")

def check_service_ready(svc):
    rc = svc.get("ready_check")
    if not rc: return True
    if rc.get("kind") == "modbus":
        return wait_modbus_ready(rc["host"], rc["port"], rc.get("timeout_sec", 10))
    return True

# -----------------------------
# Reverse dependency map
# -----------------------------
def build_reverse_deps(services):
    rev = {}
    for svc in services:
        for dep in svc.get("depends_on", []):
            rev.setdefault(dep, []).append(svc["name"])
    return rev

# -----------------------------
# Recursive Stop Logic
# -----------------------------
def stop_service_and_dependents(name, logger):
    p = processes.get(name)
    if p and p.poll() is None:
        logger.log(f"Terminating {name}")
        p.terminate()
    
    svc_ready_status[name] = False
    
    for dep_name in rev_deps.get(name, []):
        stop_service_and_dependents(dep_name, logger)

# -----------------------------
# Background Monitor Thread
# -----------------------------
def monitor_loop(logger):
    global running
    while running:
        with state_lock:
            for name, p in list(processes.items()):
                if p.poll() is not None: # プロセスが終了している
                    svc = svc_map[name]
                    if svc_ready_status.get(name): # 意図せぬ終了
                        logger.log(f"[ERROR] {name} exited unexpectedly.")
                        stop_service_and_dependents(name, logger)

                        if svc.get("type") == "plc":
                            logger.log(f"Restarting PLC: {name}")
                            cmd = [PYTHON] + svc["command"] + svc.get("args", [])
                            # 子プロセスの出力は DEVNULL へ
                            processes[name] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            
                            # 簡易的な再Ready待ち（本番はここも非同期が望ましいが、一旦シンプルに）
                            if check_service_ready(svc):
                                svc_ready_status[name] = True
                                logger.log(f"PLC {name} is READY again")
        time.sleep(1)

def show_service_logs(name, lines=20):
    """指定されたサービスの最新ログファイルの末尾を表示する"""
    with state_lock:
        if name not in svc_map:
            print(f"[!] Service '{name}' not found.")
            return

    # ログディレクトリの取得 (デフォルトは logs)
    # 本来は各svcの引数から抽出するのが理想ですが、簡易的に共通のディレクトリから探します
    log_dir = "logs" 
    
    # サービス名で始まるログファイルを検索 (例: grinder_20231010_*.log)
    search_pattern = os.path.join(log_dir, f"{name}_*.log")
    files = glob.glob(search_pattern)
    
    if not files:
        print(f"[!] No log files found for '{name}' in {log_dir}")
        return

    # 最新のファイルを選択 (更新日時順)
    latest_file = max(files, key=os.path.getmtime)
    
    print(f"\n--- Last {lines} lines of {os.path.basename(latest_file)} ---")
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            content = f.readlines()
            # 末尾20行を表示
            for line in content[-lines:]:
                print(line.strip())
    except Exception as e:
        print(f"[!] Could not read log file: {e}")
    print("-" * 50 + "\n")

# -----------------------------
# CLI Commands
# -----------------------------
def show_status(start_order):
    print("\n" + "="*75)
    print(f"{'SERVICE NAME':<15} | {'TYPE':<8} | {'PID':<8} | {'STATUS':<12} | {'READY'}")
    print("-" * 75)
    with state_lock:
        for svc in start_order:
            name = svc["name"]
            p = processes.get(name)
            pid = p.pid if p else "-"
            is_alive = p.poll() is None if p else False
            status = "Running" if is_alive else "Stopped"
            ready = "YES" if svc_ready_status.get(name) else "NO"
            print(f"{name:<15} | {svc.get('type', 'dev'):<8} | {pid:<8} | {status:<12} | {ready}")
    print("="*75 + "\n")

def interactive_log_viewer(log_dir):
    """ログディレクトリ内のファイル一覧を表示し、選択した内容を表示する"""
    # 1. ファイル一覧の取得（新しい順）
    search_pattern = os.path.join(log_dir, "*.log")
    files = sorted(glob.glob(search_pattern), key=os.path.getmtime, reverse=True)

    if not files:
        print(f"[!] No log files found in {log_dir}")
        return

    # 2. 一覧の表示
    print("\n--- Log File List (Newest first) ---")
    for i, filepath in enumerate(files):
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
        size = os.path.getsize(filepath)
        filename = os.path.basename(filepath)
        print(f"[{i:2}] {mtime} | {size:8} bytes | {filename}")
    print("-------------------------------------")

    try:
        # 3. ファイルの選択
        idx_input = input("Enter file number (or 'q' to cancel): ").strip().lower()
        if idx_input == 'q': return
        
        idx = int(idx_input)
        if not (0 <= idx < len(files)):
            print("[!] Invalid number.")
            return
        
        target_file = files[idx]

        # 4. 行数の指定
        line_input = input("Enter lines to show (default 20): ").strip()
        num_lines = int(line_input) if line_input.isdigit() else 20

        # 5. 表示
        print(f"\n--- Reading {os.path.basename(target_file)} (last {num_lines} lines) ---")
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.readlines()
            for line in content[-num_lines:]:
                print(line.strip())
        print("-" * 50 + "\n")

    except ValueError:
        print("[!] Please enter a valid number.")
    except Exception as e:
        print(f"[!] Error: {e}")

def execute_chaos(subcmd, target, logger):
    """障害注入コマンドの実行"""
    global disabled_services
    with state_lock:
        if target not in svc_map:
            print(f"[!] Service '{target}' not found.")
            return

        p = processes.get(target)

        if subcmd == "kill":
            if p and p.poll() is None:
                print(f"[*] Killing process {target} (PID: {p.pid})...")
                p.kill() # 強制終了
                # disabled に入れないので、PLCなら monitor_loop が自動復旧させる
            else:
                print(f"[!] {target} is not running.")

        elif subcmd == "stop":
            print(f"[*] Stopping {target} and disabling auto-restart...")
            disabled_services.add(target)
            if p and p.poll() is None:
                p.terminate()
            svc_ready_status[target] = False

        elif subcmd == "resume":
            if target in disabled_services:
                print(f"[*] Resuming {target}...")
                disabled_services.remove(target)
                # 次の monitor_loop またはここで明示的に起動
                svc = svc_map[target]
                cmd = [PYTHON] + svc["command"] + svc.get("args", [])
                processes[target] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                print(f"[!] {target} is not in stopped(disabled) state.")

# -----------------------------
# Main
# -----------------------------
def main():
    global running, svc_map, rev_deps

    if len(sys.argv) != 2:
        print("Usage: python orchestrator.py orchestrator.yaml")
        return

    conf = load_orchestrator_yaml(sys.argv[1])
    
    # Log Setup
    log_dir = conf.get("log", {}).get("dir", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"orchestrator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    logger = OrchestratorLogger(log_file)

    start_order = resolve_start_order(conf["services"])
    svc_map = {svc["name"]: svc for svc in start_order}
    rev_deps = build_reverse_deps(start_order)

    print(f"[*] Starting system (Log: {log_file})")
    
    # 1. 順次起動
    for svc in start_order:
        name = svc["name"]
        cmd = [PYTHON] + svc["command"] + svc.get("args", [])
        logger.log(f"Starting {name}...")
        
        # 子プロセスの標準出力を完全に抑制
        processes[name] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if check_service_ready(svc):
            svc_ready_status[name] = True
            logger.log(f"{name} is READY")
        else:
            logger.log(f"[WARN] {name} ready check failed")

    # 2. 監視スレッド開始
    m_thread = threading.Thread(target=monitor_loop, args=(logger,), daemon=True)
    m_thread.start()

    print("[!] All services process initiated. Type 'help' for commands.")

    # 3. CLI 入力ループ
    try:
        while running:
            cmd_input = input("orchestrator > ").strip().lower()
            if not cmd_input: continue

            user_input = cmd_input.split()

            cmd = user_input[0].lower()
            if len(user_input)>2:
                subcmd = user_input[1].lower()
            args = user_input[1:]
            print(">>>" + cmd)

            if cmd_input in ["status", "ls", "ps"]:
                show_status(start_order)
            elif cmd == "log":
                # インタラクティブモードを起動
                interactive_log_viewer(log_dir)
            elif cmd == "chaos":
                if len(args) < 2:
                    print("Usage: chaos <kill|stop|resume> <service_name>")
                    # print("Usage: chaos <kill|stop|resume|delay> <service_name>")
                    # print("hint!")
                    # print("Usage: chaos delay <service_name> delaySecValue")
                # elif subcmd == "delay":
                #     # 引数から秒数を取得 (例: chaos delay plc1 5)
                #     sec = int(args[3]) if len(args) > 2 else 5
                #     print(f"[*] Injecting {sec}s latency to {arg[2]}...")
                    
                #     # Modbusクライアントを使って HR 10005 に値を書き込む
                #     # (PLCのIPとポートは svc_map から取得)
                #     client = ModbusTcpClient(host, port=port)
                #     if client.connect():
                #         client.write_register(10005, sec)
                #         client.close()
                else:
                    execute_chaos(args[0], args[1], logger)
            elif cmd_input in ["help", "?"]:
                print("Available commands:")
                print("  status (ls)        : Show status of all services")
                print("  log <name> [lines] : Show recent logs for a service")
                print("  help (?)           : Show this help")
                print("  exit (quit)        : Stop all services and exit")
                print("=================================================")
                print("  chaos              : DI chaos")
            elif cmd_input in ["exit", "quit"]:
                running = False
            else:
                print(f"Unknown command: {cmd_input}")
    except (KeyboardInterrupt, EOFError):
        running = False

    # 4. 終了処理
    print("\n[*] Shutting down services...")
    with state_lock:
        for name in reversed([s["name"] for s in start_order]):
            p = processes.get(name)
            if p and p.poll() is None:
                p.terminate()
    time.sleep(1)
    print("[*] Done.")

if __name__ == "__main__":
    main()
