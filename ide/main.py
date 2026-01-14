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

        # --- ナビゲーションレールの定義 ---
        self.rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            bgcolor="#1e1e26",
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.ACCOUNT_TREE_OUTLINED,
                    selected_icon=ft.Icons.ACCOUNT_TREE,
                    label="Editor",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS,
                    label="Settings",
                ),
            ],
            on_change=self.on_nav_change,
            visible=False, # 最初は隠しておく
        )

        # 画面を入れ替えるためのコンテナ
        self.workspace_container = ft.Container(expand=True)

        # 画面を入れ替えるためのコンテナ
        self.workspace_container = ft.Container(expand=True)
        
        # 全体レイアウトを横並び(Row)にする
        self.main_layout = ft.Row(
            [
                self.rail,
                ft.VerticalDivider(width=1, color="white12", visible=False),
                self.workspace_container,
            ],
            expand=True,
            spacing=0,
        )

        self.setup_ui()

    def setup_ui(self):
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
        
        # self.page.add(self.workspace_container)
        self.page.add(self.main_layout)
        self.page.update()

        self.page.on_window_event = self.handle_window_event

    async def on_nav_change(self, e):
        """サイドバーの切り替え処理"""
        index = e.control.selected_index
        if index == 0:
            await self.load_orchestration_view()
        elif index == 1:
            await self.show_settings_view()

    async def load_orchestration_view(self):
        """ファイル選択後にOrchestrationViewへ切り替え"""
        self.rail.visible = True
        self.rail.selected_index = 0
        self.main_layout.controls[1].visible = True # Dividerを表示

        self.workspace_container.content = OrchestrationView(
            self.page, 
            self.state
        )
        self.main_layout.update()
        self.page.update()

    async def show_settings_view(self):
        """設定画面へ切り替え"""
        # load_orchestration_view を引数として渡す
        self.workspace_container.content = SettingsView(
            self.page, 
            self.load_orchestration_view
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
