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

# -----------------------------
# Orchestrator Logger (Smart Display)
# -----------------------------
class OrchestratorLogger:
    def __init__(self, log_file):
        self.log_file = log_file

    def log(self, msg, console=True):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{ts} | {msg}"
        
        # ファイルには常にすべての情報を記録
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        
        # console=True の場合のみ画面に表示
        if console:
            # # プロンプトの行を邪魔しないよう、改行を入れて出力
            # print(f"\r{line}")
            # print("orchestrator > ", end="", flush=True)

            # \r\033[K は「行頭に戻ってその行をクリアする」というエスケープシーケンスです
            # これにより、入力中の "orchestrator > " を一度消してログを出します
            sys.stdout.write(f"\r\033[K{line}\n")
            sys.stdout.write("orchestrator > ")
            sys.stdout.flush()

# -----------------------------
# Global State
# -----------------------------
running = True
processes = {}
svc_ready_status = {}
svc_map = {}
state_lock = threading.Lock()
disabled_services = set()

# -----------------------------
# Core Functions
# -----------------------------
def load_orchestrator_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def resolve_start_order(services):
    svc_map_local = {svc["name"]: svc for svc in services}
    resolved = []
    visited = set()
    def visit(name, stack):
        if name in visited: return
        if name in stack: raise ValueError(f"cyclic dependency: {name}")
        stack.add(name)
        for dep in svc_map_local[name].get("depends_on", []):
            visit(dep, stack)
        stack.remove(name)
        visited.add(name)
        resolved.append(svc_map_local[name])
    for svc in services:
        visit(svc["name"], set())
    return resolved

def check_service_ready(svc):
    rc = svc.get("ready_check")
    if not rc: return True
    if rc.get("kind") == "modbus":
        try:
            client = ModbusTcpClient(rc["host"], port=rc["port"], timeout=1)
            if client.connect():
                client.close()
                return True
        except:
            pass
    return False

# -----------------------------
# Monitoring Loop
# -----------------------------
def monitor_loop(logger, start_order):
    global running
    while running:
        with state_lock:
            for svc in start_order:
                name = svc["name"]
                if name in disabled_services: continue
                
                p = processes.get(name)
                is_alive = p and p.poll() is None

                if not is_alive:
                    # --- [ケース1] プロセスが停止している場合 ---
                    if svc_ready_status.get(name):
                        svc_ready_status[name] = False
                        logger.log(f"[ALERT] {name} has stopped unexpectedly.", console=True)
                    
                    # 再起動を試みる（親がREADYなら）
                    parent_ok = True
                    for dep in svc.get("depends_on", []):
                        if not svc_ready_status.get(dep):
                            parent_ok = False
                            break
                    
                    if parent_ok:
                        logger.log(f"Attempting to restart {name}...", console=False)
                        cmd = [PYTHON] + svc["command"] + svc.get("args", [])
                        processes[name] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                else:
                    # --- [ケース2] プロセスは動いている場合 ---
                    # 現在のREADY状態をチェックして更新する
                    current_ready = check_service_ready(svc)
                    
                    # 状態が NO -> YES に変わったときだけログを出す
                    if current_ready and not svc_ready_status.get(name):
                        svc_ready_status[name] = True
                        logger.log(f"[INFO] {name} is now READY.", console=True)
                    # 状態が YES -> NO に変わったとき（通信断など）
                    elif not current_ready and svc_ready_status.get(name):
                        svc_ready_status[name] = False
                        logger.log(f"[WARN] {name} is running but NOT READY (Modbus failure).", console=True)

        time.sleep(2)

# -----------------------------
# CLI Functions (All Features)
# -----------------------------
def show_status(start_order):
    print("\n" + "="*75)
    print(f"{'SERVICE NAME':<25} | {'TYPE':<10} | {'PID':<8} | {'STATUS':<12} | {'READY'}")
    print("-" * 75)
    with state_lock:
        for svc in start_order:
            name = svc["name"]
            p = processes.get(name)
            pid = p.pid if p else "-"
            is_alive = p.poll() is None if p else False
            status = "Running" if is_alive else "Stopped"
            ready = "YES" if svc_ready_status.get(name) else "NO"
            print(f"{name:<25} | {svc.get('type', 'dev'):<10} | {pid:<8} | {status:<12} | {ready}")
    print("="*75 + "\n")

def interactive_log_viewer(log_dir):
    search_pattern = os.path.join(log_dir, "*.log")
    files = sorted(glob.glob(search_pattern), key=os.path.getmtime, reverse=True)
    if not files:
        print(f"[!] No log files found in {log_dir}")
        return
    print("\n--- Log File List (Newest first) ---")
    for i, filepath in enumerate(files[:10]):
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
        filename = os.path.basename(filepath)
        print(f"[{i:2}] {mtime} | {filename}")
    try:
        idx_input = input("Enter file number (or 'q' to cancel): ").strip().lower()
        if idx_input == 'q': return
        idx = int(idx_input)
        target_file = files[idx]
        print(f"\n--- Reading {os.path.basename(target_file)} ---")
        with open(target_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-20:]: print(line.strip())
        print("-" * 40)
    except:
        print("[!] Invalid input.")

def execute_chaos(subcmd, target, logger, args=None):
    global disabled_services
    with state_lock:
        if target not in svc_map:
            print(f"[!] Service '{target}' not found.")
            return
        
        svc = svc_map[target]  # サービス設定を取得
        p = processes.get(target)

        if subcmd == "kill":
            if p and p.poll() is None:
                p.kill()
                logger.log(f"Chaos: Killed {target}", console=True)

        elif subcmd == "stop":
            disabled_services.add(target)
            if p and p.poll() is None:
                p.terminate()
            # 明示的にREADY状態も落とす
            svc_ready_status[target] = False
            logger.log(f"Chaos: Stopped {target} (Auto-restart disabled)", console=True)

        elif subcmd == "resume":
            if target in disabled_services:
                disabled_services.remove(target)
                logger.log(f"Chaos: Resuming {target}", console=True)
                
                # プロセスが止まっていれば再起動する ---
                # p が存在しない、または poll() が値を返している（停止中）なら起動
                if p is None or p.poll() is not None:
                    logger.log(f"Launching {target} for resume...", console=True)
                    cmd = [PYTHON] + svc["command"] + svc.get("args", [])
                    processes[target] = subprocess.Popen(
                        cmd, 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL
                    )
                    # 一度NOにしておけば、monitor_loopがModbus接続を確認してYESにしてくれます
                    svc_ready_status[target] = False
            else:
                print(f"[!] {target} is not in disabled state.")

        elif subcmd == "delay":
            if not args or len(args) < 1:
                print("Usage: chaos delay <service_name> <seconds>")
                return
            
            try:
                sec = int(args[0])
                rc = svc.get("ready_check")
                if rc and rc.get("kind") == "modbus":
                    # Modbus経由で10005番(HR_SYS_BASE + 5)に書き込む
                    client = ModbusTcpClient(rc["host"], port=rc["port"])
                    if client.connect():
                        # 10000 (Base) + 5 = 10005
                        client.write_register(10005, sec)
                        client.close()
                        logger.log(f"Chaos: Injected {sec}s latency to {target}", console=True)
                    else:
                        print(f"[!] Could not connect to {target} to inject latency.")
                else:
                    print(f"[!] Service {target} does not support Modbus chaos injection.")
            except ValueError:
                print("[!] Latency must be an integer (seconds).")




# -----------------------------
# Main Loop
# -----------------------------
def main():
    global running, svc_map
    if len(sys.argv) != 2:
        print("Usage: python orchestrator.py orchestrator.yaml")
        return

    conf = load_orchestrator_yaml(sys.argv[1])
    log_dir = conf.get("log", {}).get("dir", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"orchestrator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    logger = OrchestratorLogger(log_file)

    start_order = resolve_start_order(conf["services"])
    svc_map = {svc["name"]: svc for svc in start_order}

    print(f"[*] Starting system. Logs recorded to: {log_file}")
    for svc in start_order:
        name = svc["name"]
        cmd = [PYTHON] + svc["command"] + svc.get("args", [])
        logger.log(f"Launching {name}...", console=True)
        processes[name] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        svc_ready_status[name] = check_service_ready(svc)

    m_thread = threading.Thread(target=monitor_loop, args=(logger, start_order), daemon=True)
    m_thread.start()

    print("\n[!] System initiated. Type 'help' or '?' for commands.")

    try:
        # print("orchestrator > ", end="", flush=True)
        while running:
            cmd_input = input("orchestrator > ").strip().lower()
            # cmd_input = input("").strip().lower()
            if not cmd_input: continue
            
            parts = cmd_input.split()
            cmd = parts[0]

            if cmd in ["status", "ls", "ps"]:
                show_status(start_order)
            elif cmd == "log":
                interactive_log_viewer(log_dir)
            elif cmd == "chaos":
                if len(parts) < 3:
                    print("Usage: chaos <kill|stop|resume|delay> <service_name> [args]")
                else:
                    execute_chaos(parts[1], parts[2], logger, args=parts[3:])
            elif cmd in ["help", "?"]:
                print("\nAvailable commands:")
                print("  status (ls, ps)    : Show status of all services")
                print("  log                : Open interactive log viewer")
                print("  chaos kill <name>  : Force kill a service (auto-restart enabled)")
                print("  chaos stop <name>  : Stop a service and disable auto-restart")
                print("  chaos resume <name>: Re-enable and start a stopped service")
                print("  chaos delay <name> <sec> : Inject Modbus latency (0 to disable)")
                print("  help (?)           : Show this help")
                print("  exit (quit)        : Stop all services and exit\n")
            elif cmd in ["exit", "quit"]:
                running = False
            else:
                print(f"Unknown command: {cmd}")
    except (KeyboardInterrupt, EOFError):
        running = False

    print("\n[*] Shutting down services...")
    for name in reversed([s["name"] for s in start_order]):
        p = processes.get(name)
        if p and p.poll() is None: p.terminate()
    print("[*] Done.")

if __name__ == "__main__":
    main()