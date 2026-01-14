import os

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