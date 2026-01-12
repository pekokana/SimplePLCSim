import flet as ft
import yaml
import os

class OrchestrationView(ft.Container):
    def __init__(self, page: ft.Page, state):
        super().__init__(
            expand=True,
            padding=20,
            bgcolor="#1a1c1e"
        )
        self.app_page = page
        self.app_state = state

        # 1. リストを表示する部品
        self.list_view = ft.ListView(
            expand=True, 
            spacing=10, 
            padding=10,
        )

        # 2. メインレイアウト
        self.content = ft.Column([
            # ヘッダーエリア
            ft.Row([
                ft.Column([
                    ft.Text("Orchestration Editor", size=30, weight="bold", color="white"),
                    ft.Text(f"File: {os.path.basename(self.app_state.orchestration_file)}", color="grey", size=12),
                ]),
                # 操作ボタン
                ft.Row([
                    ft.IconButton(
                        icon=ft.Icons.PLAY_ARROW, # キーワード引数で指定
                        icon_color="green400", 
                        tooltip="Start All", 
                        on_click=self.start_all
                    ),
                    ft.IconButton(
                        icon=ft.Icons.STOP, # キーワード引数で指定
                        icon_color="red400", 
                        tooltip="Stop All", 
                        on_click=self.stop_all
                    ),
                    ft.VerticalDivider(),
                    ft.Button(
                        content="Reload", 
                        icon=ft.Icons.REFRESH, 
                        on_click=lambda _: self.load_yaml_and_build_ui()
                    ),
                ])
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=20, color="white24"),
            self.list_view
        ], expand=True)

    def did_mount(self):
        self.load_yaml_and_build_ui()

    def load_yaml_and_build_ui(self):
        self.list_view.controls.clear()
        if not self.page: return

        try:
            with open(self.app_state.orchestration_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            services = data.get("services", [])
            for svc in services:
                self.list_view.controls.append(self.create_service_card(svc))
                
        except Exception as e:
            self.list_view.controls.append(ft.Text(f"Error: {str(e)}", color="red"))

        self.update()

    def create_service_card(self, svc):
        svc_name = str(svc.get("name", "Unnamed"))
        svc_type = str(svc.get("type", "unknown")).lower()
        
        icon_map = {
            "plc": (ft.Icons.MEMORY, "blue400"),
            "device": (ft.Icons.SENSORS, "green400"),
            "iodevice": (ft.Icons.HUB, "orange400")
        }
        icon_name, icon_color = icon_map.get(svc_type, (ft.Icons.QUESTION_MARK, "grey400"))

        return ft.Container(
            bgcolor="#2c2e33",
            border_radius=8,
            padding=5,
            content=ft.ListTile(
                leading=ft.Icon(icon_name, color=icon_color),
                title=ft.Text(svc_name, color="white", weight="bold"),
                subtitle=ft.Text(f"Type: {svc_type}", color="grey400"),
                trailing=ft.IconButton(
                    icon=ft.Icons.SETTINGS, # キーワード引数で指定
                    icon_color="white54",
                    # lambda内で現在の svc_name を固定するために引数として渡す
                    on_click=lambda e, name=svc_name: print(f"Settings for {name}")
                ),
            )
        )

    def start_all(self, e):
        print("Starting all services...")

    def stop_all(self, e):
        print("Stopping all services...")