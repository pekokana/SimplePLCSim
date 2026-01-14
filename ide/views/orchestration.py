import flet as ft
import yaml
import os
from models.config_manager import ConfigManager

class OrchestrationView(ft.Container):
    def __init__(self, page: ft.Page, state):
        super().__init__(
            expand=True,
            padding=20,
            bgcolor="#1a1c1e"
        )
        self.app_page = page
        self.app_state = state
        self.config_manager = ConfigManager()

        # ファイル名の表示を安全にする
        file_path = self.app_state.orchestration_file
        display_name = os.path.basename(file_path) if file_path and os.path.exists(file_path) else "New Project"

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
                    # ここを安全な名前に差し替え
                    ft.Text(f"File: {display_name}", color="grey", size=12),
                ]),
                # 操作ボタン
                ft.Row([
                    # --- サービス追加ボタン群 ---
                    ft.PopupMenuButton(
                        items=[
                            ft.PopupMenuItem(content="Add PLC", icon=ft.Icons.MEMORY, on_click=lambda _: self.add_service("plc")),
                            ft.PopupMenuItem(content="Add Device", icon=ft.Icons.SENSORS, on_click=lambda _: self.add_service("device")),
                            ft.PopupMenuItem(content="Add IO Device", icon=ft.Icons.HUB, on_click=lambda _: self.add_service("iodevice")),
                        ],
                        menu_position=ft.PopupMenuPosition.UNDER,
                        # icon=icon=ft.Icons.ADD
                    ),
                    ft.VerticalDivider(),
                    # --- 保存ボタン ---
                    ft.IconButton(
                        icon=ft.Icons.SAVE,
                        icon_color="blue400",
                        tooltip="Save YAML",
                        on_click=self.save_yaml
                    ),
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
        
        # 1. 新規プロジェクト（ファイルがまだ存在しない）場合
        if not self.app_state.orchestration_file or not os.path.exists(self.app_state.orchestration_file):
            # 状態管理にある初期データを使ってUIを構築
            services = self.app_state.config_data.get("services", [])
            if not services:
                self.list_view.controls.append(
                    ft.Text("No services defined. Click '+' to add (TBD).", color="grey")
                )
            else:
                for svc in services:
                    self.list_view.controls.append(self.create_service_card(svc))
            self.update()
            return

        # 2. 既存ファイルがある場合（従来のロジック）
        try:
            with open(self.app_state.orchestration_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                # AppStateに反映させておく
                self.app_state.config_data = data 

            services = data.get("services", [])
            for svc in services:
                self.list_view.controls.append(self.create_service_card(svc))
        except Exception as e:
            self.list_view.controls.append(ft.Text(f"Error: {str(e)}", color="red"))

        self.update()

    def add_service(self, svc_type):
        """新しいサービスをAppStateのデータ構造に追加してUIを再構築"""
        new_svc = {
            "name": f"new_{svc_type}_{len(self.app_state.config_data.get('services', [])) + 1}",
            "type": svc_type,
            "image": f"simpleplcsim/{svc_type}:latest", # デフォルトイメージ
            "networks": ["plc_net"]
        }
        
        if "services" not in self.app_state.config_data:
            self.app_state.config_data["services"] = []
        
        self.app_state.config_data["services"].append(new_svc)
        self.load_yaml_and_build_ui() # 再描画

    def save_yaml(self, e):
        """現在のAppStateをYAMLとして書き出す。この時設定画面のパスを適用する"""
        try:
            # 1. 保存先パスの決定（新規の場合はFilePickerを出すのが理想ですが、一旦既存/デフォルトへ）
            save_path = self.app_state.orchestration_file
            if not save_path or save_path == "Untitled":
                # 本来はここでFilePickerを呼び出すべきですが、簡易的に固定またはAppStateの初期値
                save_path = "orchestrator.yaml"

            # 2. ConfigManagerからパスを取得して、services内のcommandを更新
            engines = self.config_manager.config_data.get("engines", {})
            
            # 書き出し用のコピーを作成
            export_data = self.app_state.config_data.copy()
            
            for svc in export_data.get("services", []):
                svc_type = svc.get("type")
                if svc_type in engines and engines[svc_type]:
                    # 設定画面で保存したパスを command フィールドにセット
                    svc["command"] = engines[svc_type]

            # 3. YAML書き出し
            with open(save_path, "w", encoding="utf-8") as f:
                yaml.dump(export_data, f, default_flow_style=False, sort_keys=False)

            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Saved to {save_path}"))
            self.app_page.snack_bar.open = True
            self.app_page.update()

        except Exception as ex:
            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Save failed: {str(ex)}"))
            self.app_page.snack_bar.open = True
            self.app_page.update()

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

    def load_yaml_and_build_ui(self):
        self.list_view.controls.clear()
        
        # 既存ファイルの読み込み、またはAppStateのデータをそのまま使用
        if self.app_state.orchestration_file and os.path.exists(str(self.app_state.orchestration_file)):
            try:
                with open(self.app_state.orchestration_file, "r", encoding="utf-8") as f:
                    self.app_state.config_data = yaml.safe_load(f)
            except:
                pass

        services = self.app_state.config_data.get("services", [])
        for svc in services:
            self.list_view.controls.append(self.create_service_card(svc))
        
        self.update()

    def start_all(self, e):
        print("Starting all services...")

    def stop_all(self, e):
        print("Stopping all services...")