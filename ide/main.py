import flet as ft
from state import AppState
from views.welcome import WelcomeView
from views.orchestration import OrchestrationView
from views.settings_view import SettingsView
import asyncio
import sys
from models.config_manager import ConfigManager

class PLCSimApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.config_manager = ConfigManager()

        self.state = AppState()

        # 画面を入れ替えるためのコンテナ
        self.workspace_container = ft.Container(expand=True)
        
        self.setup_ui()

    def setup_ui(self):
        # # ファイル選択機能の登録
        # self.file_picker = ft.FilePicker()
        # self.page.overlay.append(self.file_picker)
        # # タイトルなどの設定の前に一度画面をupdateして登録を完了させる
        # self.page.update()

        # メイン画面の設定
        self.page.title = "SimplePLCSim IDE"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        
        # 初期画面としてWelcome画面を表示
        self.workspace_container.content = WelcomeView(
            self.page, 
            self.state, 
            self.load_orchestration_view
        )
        
        self.page.add(self.workspace_container)
        self.page.update()

        self.page.on_window_event = self.handle_window_event

    async def load_orchestration_view(self):
        """ファイル選択後にOrchestrationViewへ切り替え"""
        self.workspace_container.content = OrchestrationView(
            self.page, 
            self.state
        )
        self.page.update()

    async def back_to_welcome(self):
        self.workspace_container.content = WelcomeView(
            self.page, self.state, self.load_orchestration_view
        )
        self.page.update()

    async def handle_window_event(self, e):
        if e.data == "close":
            # ここで orchestrator.py のプロセスなどが動いていれば terminate() する
            print("Closing IDE...")
            self.page.window_destroy()

async def main(page: ft.Page):
    # ウィンドウが閉じられた時の処理を追加
    def handle_window_event(e):
        if e.data == "close":
            page.window_destroy()

    page.on_window_event = handle_window_event

    PLCSimApp(page)
    page.update()

if __name__ == "__main__":
    ft.run(main)
