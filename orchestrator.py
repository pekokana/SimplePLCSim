import yaml
import subprocess
import sys
import time
from datetime import datetime
import os

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
        print(line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

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
# Main
# -----------------------------
def main():
    global log

    if len(sys.argv) != 2:
        log("Usage: python orchestrator.py orchestrator.yaml")
        sys.exit(1)

    conf = load_orchestrator_yaml(sys.argv[1])
    services = conf["services"]

    # -----------------------------
    # Log setup
    # -----------------------------
    log_conf = conf.get("log", {})
    log_dir = log_conf.get("dir", "logs")

    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"orchestrator_{timestamp}.log")

    logger = OrchestratorLogger(log_file)
    log = logger.log

    log(f"[orchestrator] log file = {log_file}")

    start_order = resolve_start_order(services)
    rev_deps = build_reverse_deps(start_order)

    processes = {}  # name -> Popen
    svc_map = {svc["name"]: svc for svc in start_order}

    # -----------------------------
    # Recursive stop
    # -----------------------------
    stopped = set()

    def stop_service_and_dependents(name):
        if name in stopped:
            return

        for dep in rev_deps.get(name, []):
            stop_service_and_dependents(dep)

        p = processes.get(name)
        if p and p.poll() is None:
            log(f"[orchestrator] terminate {name}")
            p.terminate()

        stopped.add(name)

    try:
        # -----------------------------
        # Start services
        # -----------------------------
        for svc in start_order:
            name = svc["name"]
            cmd = [PYTHON] + svc["command"] + svc.get("args", [])

            log(f"[orchestrator] starting {name}: {' '.join(cmd)}")
            processes[name] = subprocess.Popen(cmd)

            while not wait_service_ready(svc):
                time.sleep(1)

        log("[orchestrator] all services started")

        # -----------------------------
        # Monitor loop
        # -----------------------------
        while True:
            for name, p in list(processes.items()):
                if p.poll() is not None:
                    svc = svc_map[name]
                    log(f"[orchestrator][ERROR] {name} exited")

                    # ---- device / plc 共通: 巻き込み停止 ----
                    stop_service_and_dependents(name)

                    # ---- PLC だけは再起動 ----
                    if svc.get("type") == "plc":
                        log(f"[orchestrator] restarting PLC {name}")
                        cmd = [PYTHON] + svc["command"] + svc.get("args", [])
                        processes[name] = subprocess.Popen(cmd)
                        stopped.discard(name)

                        while not wait_service_ready(svc):
                            time.sleep(1)

                        log(f"[orchestrator] PLC {name} READY again")

            time.sleep(1)

    except KeyboardInterrupt:
        log("\n[orchestrator] stopping services...")

    finally:
        for name in reversed(list(processes.keys())):
            p = processes.get(name)
            if p and p.poll() is None:
                log(f"[orchestrator] terminate {name}")
                p.terminate()

        time.sleep(2)

        for name in reversed(list(processes.keys())):
            p = processes.get(name)
            if p and p.poll() is None:
                log(f"[orchestrator] kill {name}")
                p.kill()

        log("[orchestrator] shutdown complete")

if __name__ == "__main__":
    main()
