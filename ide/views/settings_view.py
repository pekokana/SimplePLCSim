import asyncio
import flet as ft
from models.config_manager import ConfigManager

class SettingsView(ft.Container):
    def __init__(self, page: ft.Page, on_back_to_editor):
        super().__init__(expand=True, padding=40, bgcolor="#1a1c1e")
        self.app_page = page
        self.on_back_to_editor = on_back_to_editor
        self.config = ConfigManager()

        # 1. 実行ファイルパスのフィールド
        self.orch_path = self._create_path_field("Orchestrator (orchestrator.exe)", "orchestrator") 
        self.plc_path = self._create_path_field("PLC Simulator (plcsim.exe)", "plc")
        self.device_path = self._create_path_field("Device Simulator (devicesim.exe)", "device")
        self.iodevice_path = self._create_path_field("IO Device Simulator (iodevicesim.exe)", "iodevice")

        # 2. 命名規則のフィールド
        naming = self.config.config_data.get("naming", {})
        self.naming_plc = ft.TextField(label="PLC Pattern", value=naming.get("plc", "plc_{name}.yaml"), expand=True)
        self.naming_device = ft.TextField(label="Device Pattern", value=naming.get("device", "dev_{name}.yaml"), expand=True)
        self.naming_iodev = ft.TextField(label="IODevice Pattern", value=naming.get("iodevice", "io_{name}.yaml"), expand=True)
        self.naming_ladder = ft.TextField(label="Ladder Pattern", value=naming.get("ladder", "ld_{name}.yaml"), expand=True)

        self.content = ft.Column([
            ft.Text("Environment Settings", size=32, weight="bold", color="white"),
            ft.Text("Configure paths and naming rules for the simulation system.", color="grey"),
            ft.Divider(height=40, color="white24"),
            
            # セクション: シミュレータ本体
            ft.Text("Simulator Executables", size=20, weight="bold", color="blue200"),
            self.orch_path,
            self.plc_path,
            self.device_path,
            self.iodevice_path,
            
            ft.Divider(height=40, color="white24"),

            # セクション: 命名規則
            ft.Text("YAML Naming Conventions", size=20, weight="bold", color="blue200"),
            ft.Text("Use {name} as a placeholder for the service name.", size=12, color="grey"),
            ft.Row([self.naming_plc, self.naming_device]),
            ft.Row([self.naming_iodev, self.naming_ladder]),
            
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
        engines = self.config.config_data.get("engines", {})
        current_value = engines.get(key, "")
        text_field = ft.TextField(label=label, value=current_value, expand=True, border_color="blue700")
        
        return ft.Row([
            text_field,
            ft.IconButton(
                icon=ft.Icons.FOLDER_OPEN,
                on_click=lambda _: self.app_page.run_task(self.handle_pick_file, text_field)
            )
        ])

    async def handle_pick_file(self, target_field):
        files = await ft.FilePicker().pick_files(allowed_extensions=["exe"], allow_multiple=False)
        if files and len(files) > 0:
            target_field.value = files[0].path
            target_field.update()

    async def save_settings(self, e):
        # パスの保存
        self.config.config_data["engines"] = {
            "orchestrator": self.orch_path.controls[0].value,
            "plc": self.plc_path.controls[0].value,
            "device": self.device_path.controls[0].value,
            "iodevice": self.iodevice_path.controls[0].value,
        }
        
        # 命名規則の保存
        self.config.config_data["naming"] = {
            "plc": self.naming_plc.value,
            "device": self.naming_device.value,
            "iodevice": self.naming_iodev.value,
            "ladder": self.naming_ladder.value,
        }
        
        self.config.save()
        
        self.app_page.snack_bar = ft.SnackBar(ft.Text("Settings saved successfully!"), bgcolor=ft.Colors.GREEN_700)
        self.app_page.snack_bar.open = True
        self.app_page.update()

        await asyncio.sleep(1)
        await self.on_back_to_editor()