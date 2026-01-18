import flet as ft

class PlcEditorView(ft.Container):
    def __init__(self, page: ft.Page, state, svc, on_back):
        super().__init__(expand=True, padding=30, bgcolor="#1a1c1e")
        self.app_page = page
        self.app_state = state
        self.svc = svc
        self.on_back = on_back

        # --- 各種入力フィールドの生成 ---
        # 基本情報
        self.name_field = ft.TextField(label="PLC Name", value=self.svc.get("name", ""), border_radius=8)
        # Log Directory フィールド
        self.log_dir_field = ft.TextField(
            label="Log Directory", 
            value=self.svc.get("log_dir", "logs"), 
            border_radius=8,
            read_only=True,
            expand=True
        )

        # CPU設定
        cpu_cfg = self.svc.get("cpu", {})
        self.scan_cycle_field = ft.TextField(
            label="Scan Cycle (ms)", 
            value=str(cpu_cfg.get("scan_cycle_ms", 100)),
            suffix="ms", 
            width=200,
            border_radius=8
        )

        # Modbus設定
        mb_cfg = self.svc.get("modbus", {})
        self.port_field = ft.TextField(
            label="Modbus Port", 
            value=str(mb_cfg.get("port", 15030)),
            width=200,
            border_radius=8
        )

        # メモリ設定 (memory.X, Y, M, D)
        mem_cfg = self.svc.get("memory", {})
        self.x_input = self.create_mem_field("X (Input)", mem_cfg.get("X", 5))
        self.y_input = self.create_mem_field("Y (Output)", mem_cfg.get("Y", 5))
        self.m_input = self.create_mem_field("M (Internal Relay)", mem_cfg.get("M", 10))
        self.d_input = self.create_mem_field("D (Data Register)", mem_cfg.get("D", 10))

        # 構築
        self.content = ft.Column([
            # ヘッダー
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.on_back(), icon_color="white54"),
                ft.Icon(ft.Icons.MEMORY, color="blue400", size=30),
                ft.Text(f"PLC Configuration Details", size=24, weight="bold"),
                ft.VerticalDivider(),
                ft.Text(f"Type: {self.svc.get('kind', 'plc')} v{self.svc.get('version', '1.0')}", color="grey500")
            ], spacing=20),

            ft.Divider(height=30, color="white24"),

            ft.Row([
                # 左カラム: 基本 & 通信設定
                ft.Column([
                    self.create_section_title("Basic & CPU Settings"),
                    self.name_field,
                    
                    # ログディレクトリ選択行
                    ft.Row([
                        self.log_dir_field,
                        ft.IconButton(
                            icon=ft.Icons.FOLDER_OPEN,
                            # run_taskを使用して非同期ハンドラを呼び出す
                            on_click=lambda _: self.app_page.run_task(self.handle_pick_directory)
                        )
                    ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.END),

                    self.scan_cycle_field,
                    
                    ft.Divider(color="transparent"),
                    
                    self.create_section_title("Communication (Modbus)"),
                    self.port_field,

                    ft.Divider(height=40, color="transparent"),
                    ft.ElevatedButton(
                        "Apply Changes", 
                        icon=ft.Icons.SAVE, 
                        # on_click=lambda _: self.app_page.run_task(self.save_settings),
                        on_click=self.save_settings,
                        bgcolor="blue700",
                        color="white",
                        height=50,
                        width=300
                    )
                ], expand=1, spacing=15),

                # 右カラム: メモリ設定 & プレビュー
                ft.Column([
                    self.create_section_title("Memory Points Allocation"),
                    ft.Row([self.x_input, self.y_input], spacing=10),
                    ft.Row([self.m_input, self.d_input], spacing=10),
                    
                    ft.Divider(color="transparent"),
                    
                    ft.Container(
                        bgcolor="#25282d",
                        padding=20,
                        border_radius=12,
                        content=ft.Column([
                            ft.Text("Memory Map Quick Reference", weight="bold", color="blue200"),
                            ft.Text("X: 0 - (N-1) [Discrete Input]", size=12),
                            ft.Text("Y: 0 - (N-1) [Coil]", size=12),
                            ft.Text("M: 1000 - (1000+N-1) [Coil]", size=12),
                            ft.Text("D: 0 - (N-1) [Holding Register]", size=12),
                            ft.Divider(color="white10"),
                            ft.Text("System info starts at 10000", size=11, color="grey500")
                        ])
                    )
                ], expand=1, spacing=15)
            ], alignment=ft.CrossAxisAlignment.START, spacing=50)
        ], scroll=ft.ScrollMode.AUTO)

    # --- 非同期でのディレクトリ選択ハンドラ ---
    # e=None とすることで、run_task から引数なしで呼ばれてもエラーになりません
    async def handle_pick_directory(self, e=None):
        """overlayへの追加不要な await スタイル"""
        path = await ft.FilePicker().get_directory_path(
            dialog_title="Select Log Directory"
        )
        if path:
            self.log_dir_field.value = path
            self.log_dir_field.update()


    def create_section_title(self, text):
        return ft.Text(text, size=16, weight="bold", color="blue400")

    def create_mem_field(self, label, val):
        return ft.TextField(label=label, value=str(val), width=180, border_radius=8, suffix="pts")

    def save_settings(self, e=None):
        try:
            # 構造に従って値を格納
            self.svc["kind"] = "plc"
            self.svc["version"] = "1.0"
            self.svc["name"] = self.name_field.value
            self.svc["log_dir"] = self.log_dir_field.value
            self.svc["power"] = True # 固定値
            
            self.svc["cpu"] = {"scan_cycle_ms": int(self.scan_cycle_field.value)}
            self.svc["modbus"] = {"port": int(self.port_field.value)}
            
            self.svc["memory"] = {
                "X": int(self.x_input.value),
                "Y": int(self.y_input.value),
                "M": int(self.m_input.value),
                "D": int(self.d_input.value)
            }
            
            # 一覧に戻る
            self.on_back(f"PLC '{self.name_field.value}' updated in memory.")
        except ValueError:
            self.app_page.snack_bar = ft.SnackBar(ft.Text("Invalid number format. Please check your inputs."))
            self.app_page.snack_bar.open = True
            self.app_page.update()