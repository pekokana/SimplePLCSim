# ide/models/config_manager.py (拡張版)
import yaml
import os
import sys

class ConfigManager:
    def __init__(self, filename="simpleplcsimide.yaml"):
        # IDE実行ディレクトリを基準にする
        self.base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.config_path = os.path.join(self.base_dir, filename)
        
        # デフォルト構造
        self.config_data = {
            "engines": {
                "plc": "",
                "device": "",
                "iodevice": ""
            },
            "last_opened_project": ""
        }
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data: self.config_data.update(data)

    def save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config_data, f, default_flow_style=False)