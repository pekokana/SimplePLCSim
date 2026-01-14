import asyncio
import flet as ft
from models.config_manager import ConfigManager

class SettingsView(ft.Container):
    def __init__(self, page: ft.Page, on_back_to_editor):
        super().__init__(expand=True, padding=40, bgcolor="#1a1c1e")
        self.app_page = page
        self.on_back_to_editor = on_back_to_editor # 戻り先関数を保持
        self.config = ConfigManager()
        self.expand = True

        # 各パス入力用フィールド
        self.orch_path = self._create_path_field("Orchestrator (orchestrator.exe)", "orchestrator") 
        self.plc_path = self._create_path_field("PLC Simulator (plcsim.exe)", "plc")
        self.device_path = self._create_path_field("Device Simulator (devicesim.exe)", "device")
        self.iodevice_path = self._create_path_field("IO Device Simulator (iodevicesim.exe)", "iodevice")

        self.content = ft.Column([
            ft.Text("Environment Settings", size=32, weight="bold", color="white"),
            ft.Text("Configure the executable paths for each simulation engine.", color="grey"),
            ft.Divider(height=40, color="white24"),
            
            ft.Text("Simulator Executables", size=20, weight="bold"),
            self.orch_path,
            self.plc_path,
            self.device_path,
            self.iodevice_path,
            
            ft.Row([
                ft.ElevatedButton(
                    "Save Settings", 
                    icon="save", 
                    on_click=self.save_settings,
                    style=ft.ButtonStyle(bgcolor="blue700", color="white")
                )
            ], alignment="end", margin=20)
        ], scroll=ft.ScrollMode.AUTO)

    def _create_path_field(self, label, key):
        # 現在の保存値を取得
        engines = self.config.config_data.get("engines", {})
        current_value = engines.get(key, "")

        text_field = ft.TextField(
            label=label,
            value=current_value,
            expand=True,
            border_color="blue700"
        )
        
        return ft.Row([
            text_field,
            ft.IconButton(
                icon=ft.Icons.FOLDER_OPEN,
                on_click=lambda _: self.app_page.run_task(self.handle_pick_file, text_field)
            )
        ])

    async def handle_pick_file(self, target_field):
        """公式の最新ドキュメント通りの await スタイル"""
        # overlay への append 不要！
        files = await ft.FilePicker().pick_files(
            allowed_extensions=["exe"],
            allow_multiple=False
        )
        
        if files and len(files) > 0:
            target_field.value = files[0].path
            target_field.update()


    async def save_settings(self, e):
        self.config.config_data["engines"]["orchestrator"] = self.orch_path.controls[0].value
        self.config.config_data["engines"]["plc"] = self.plc_path.controls[0].value
        self.config.config_data["engines"]["device"] = self.device_path.controls[0].value
        self.config.config_data["engines"]["iodevice"] = self.iodevice_path.controls[0].value
        self.config.save()
        
        # 2. スナックバー（トースター）を表示
        self.app_page.snack_bar = ft.SnackBar(
            ft.Text("Settings saved successfully!"),
            bgcolor=ft.Colors.GREEN_700 # 成功っぽく緑色に
        )
        self.app_page.snack_bar.open = True
        self.app_page.update()

        # 3. ユーザーが通知を確認できる程度に少し待つ (1秒)
        await asyncio.sleep(1)

        # 4. OrchestrationViewに戻る
        # main.pyの load_orchestration_view を実行
        await self.on_back_to_editor()