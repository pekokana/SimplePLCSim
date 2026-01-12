import os

class AppState:
    def __init__(self):
        self.orchestration_file = None  # 親YAMLのパス
        self.project_dir = None         # 作業ディレクトリ
        self.nodes = []                 # 読み込んだノードリスト
        
    def set_project(self, file_path):
        self.orchestration_file = file_path
        self.project_dir = os.path.dirname(file_path)