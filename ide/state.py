import os
import yaml

class AppState:
    def __init__(self):
        self.orchestration_file = None  # 親YAMLのパス
        self.config_data = {}
        self.project_dir = None         # 作業ディレクトリ
        self.nodes = []                 # 読み込んだノードリスト
        
    def set_project(self, file_path):
        self.orchestration_file = file_path
        self.project_dir = os.path.dirname(file_path)

    def create_new_project(self):
        """新規プロジェクトとして初期化"""
        # まだ保存されていないことを示すために、空文字または特定のラベルを入れる
        self.orchestration_file = "Untitled" 
        self.config_data = {
            "networks": {"plc_net": {"driver": "bridge"}},
            "services": [] # リスト形式で初期化（orchestration.pyの読み込みロジックに合わせる）
        }

    def save_all(self, orchestrator_path, naming_rules, engine_paths):
        try:
            base_dir = os.path.dirname(orchestrator_path)
            services_summary = []

            for svc in self.nodes:
                kind = svc.get("type")
                name = svc.get("name", "unnamed")
                
                # 命名規則に従ったファイル名
                pattern = naming_rules.get(kind, f"{kind}_{{name}}.yaml")
                filename = pattern.format(name=name)
                full_path = os.path.join(base_dir, filename)

                # --- サービス種別ごとのデータ構造構築 ---
                content = {"kind": kind, "version": "1.0"}

                if kind == "plc":
                    content.update({
                        "name": name, "log_dir": "logs", "power": True,
                        "cpu": {"scan_cycle_ms": int(svc.get("scan_cycle_ms", 100))},
                        "memory": {"X": 100, "Y": 100, "M": 1000, "D": 1000},
                        "modbus": {"port": int(svc.get("port", 15020))}
                    })
                elif kind == "device":
                    content["device"] = {
                        "name": name, "log_dir": "logs",
                        "plc": {"host": svc.get("plc_host", "localhost"), "port": int(svc.get("plc_port", 15020))},
                        "cycle_ms": int(svc.get("cycle_ms", 100)),
                        "signals": svc.get("signals", {}) # 詳細エディタで編集
                    }
                elif kind == "iodevice":
                    content.update({
                        "name": name, "cycle_ms": int(svc.get("cycle_ms", 200)), "log_dir": "logs",
                        "connections": svc.get("connections", [])
                    })

                # 個別ファイル保存
                with open(full_path, "w", encoding="utf-8") as f:
                    yaml.dump(content, f, sort_keys=False, allow_unicode=True)

                # --- オーケストレーター用エントリ ---
                # command に Settings 画面で指定されたパスをセット
                exec_path = engine_paths.get(kind, f"{kind}sim.py")

                # --- オーケストレーター用エントリ構築 ---
                entry = {
                    "name": name,
                    "type": kind,
                    "command": [exec_path], # 実行ファイル名
                    "args": [filename] # 引数に個別YAMLを指定
                }

                # UIで設定された depends_on があれば追加
                if svc.get("depends_on"):
                    entry["depends_on"] = svc.get("depends_on")

                # PLCの場合はラダーパスを追加（命名規則通りなら）
                if kind == "plc":
                    ld_file = naming_rules.get("ladder", "ld_{name}.yaml").format(name=name)
                    entry["args"].append(ld_file)
                    entry["ready_check"] = {"kind": "modbus", "host": "127.0.0.1", "port": int(svc.get("port", 15020))}
                
                services_summary.append(entry)

            # オーケストレーター本体の保存
            orch_data = {
                "kind": "orchestrator", "version": "1.0", "log": {"dir": "logs"},
                "services": services_summary
            }
            with open(orchestrator_path, "w", encoding="utf-8") as f:
                yaml.dump(orch_data, f, sort_keys=False, allow_unicode=True)

            return True, "Success"
        except Exception as e:
            return False, str(e)