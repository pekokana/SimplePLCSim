import flet as ft
from models.config_manager import ConfigManager

class SettingsView(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__(expand=True, padding=40, bgcolor="#1a1c1e")
        self.page = page
        self.config = ConfigManager()

        # 各パス入力用フィールド
        self.plc_path = self._create_path_field("PLC Simulator (plcsim.exe)", "plc")
        self.device_path = self._create_path_field("Device Simulator (devicesim.exe)", "device")
        self.iodevice_path = self._create_path_field("IO Device Simulator (iodevicesim.exe)", "iodevice")

        self.content = ft.Column([
            ft.Text("Environment Settings", size=32, weight="bold", color="white"),
            ft.Text("Configure the executable paths for each simulation engine.", color="grey"),
            ft.Divider(height=40, color="white24"),
            
            ft.Text("Simulator Executables", size=20, weight="bold"),
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
            ], alignment="end", mt=20)
        ], scroll=ft.ScrollMode.AUTO)

    def _create_path_field(self, label, key):
        current_value = self.config.config_data["engines"].get(key, "")
        text_field = ft.TextField(
            label=label,
            value=current_value,
            expand=True,
            border_color="blue700"
        )
        
        # ファイル選択
        pick_files_dialog = ft.FilePicker(
            on_result=lambda e: self._on_file_result(e, text_field)
        )
        self.page.overlay.append(pick_files_dialog)

        return ft.Row([
            text_field,
            ft.IconButton(
                icon="folder_open",
                on_click=lambda _: pick_files_dialog.pick_files(
                    allow_multiple=False,
                    allowed_extensions=["exe"]
                )
            )
        ])

    def _on_file_result(self, e: ft.FilePickerUploadEvent, target_field):
        if e.files:
            target_field.value = e.files[0].path
            target_field.update()

    def save_settings(self, e):
        self.config.config_data["engines"]["plc"] = self.plc_path.controls[0].value
        self.config.config_data["engines"]["device"] = self.device_path.controls[0].value
        self.config.config_data["engines"]["iodevice"] = self.iodevice_path.controls[0].value
        self.config.save()
        
        self.page.snack_bar = ft.SnackBar(ft.Text("Settings saved successfully!"))
        self.page.snack_bar.open = True
        self.page.update()