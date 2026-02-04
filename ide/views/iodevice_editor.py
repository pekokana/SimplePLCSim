import flet as ft
import asyncio
from utils.yaml_utils import rename_entity

class IoDeviceEditorView(ft.Container):
    def __init__(self, page: ft.Page, state, svc, on_back):

        if svc is None:
            super().__init__(
                content=ft.Column([
                    ft.Text("IoDevice YAML not found.", color="red"),
                    ft.ElevatedButton("Back", on_click=lambda _: on_back("IoDevice YAML not found"))
                ])
            )
            return

        super().__init__(expand=True, padding=30, bgcolor="#1a1c1e")
        self.app_page = page
        self.app_state = state
        self.svc = svc
        self.on_back = on_back

        # --- 基本設定 ---
        self.name_field = ft.TextField(label="Service Name", value=svc.get("name", ""), border_radius=8)
        self.cycle_field = ft.TextField(label="Cycle (ms)", value=str(svc.get("cycle_ms", 200)), width=150, border_radius=8, suffix="ms")
        self.log_dir_field = ft.TextField(label="Log Directory", value=svc.get("log_dir", "logs"), read_only=True, expand=True)

        self.conn_column = ft.Column(spacing=20, scroll=ft.ScrollMode.AUTO, expand=True)
        
        # 初期ロード
        self.load_connections(do_update=False)

        self.content = ft.Column([
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.on_back(), icon_color="white54"),
                ft.Icon(ft.Icons.HUB, color="orange400", size=30),
                ft.Text("IODevice Bridge Editor", size=24, weight="bold"),
            ], spacing=20),

            ft.Divider(color="white24"),

            ft.Row([
                # 左：設定
                ft.Column([
                    ft.Text("General Settings", size=16, weight="bold", color="orange400"),
                    self.name_field,
                    self.cycle_field,
                    ft.Row([self.log_dir_field, ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=lambda _: self.app_page.run_task(self.handle_pick_directory))]),
                    ft.Divider(color="transparent"),
                    ft.ElevatedButton("Apply Changes", icon=ft.Icons.CHECK, on_click=self.save_settings, bgcolor="blue700", width=300, height=50),
                ], width=300, spacing=15),

                ft.VerticalDivider(width=1),

                # 右：Connections
                ft.Column([
                    ft.Row([
                        ft.Text("Bridge & Action Connections", size=16, weight="bold", color="orange400"),
                        ft.ElevatedButton("Add Connection", icon=ft.Icons.ADD, on_click=self.add_connection_ui)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    self.conn_column
                ], expand=True)
            ], expand=True, alignment=ft.CrossAxisAlignment.START)
        ])

    def load_connections(self, do_update=True):
        self.conn_column.controls.clear()
        conns = self.svc.get("connections", [])
        for conn_data in conns:
            self.conn_column.controls.append(self.create_connection_card(conn_data))
        if do_update:
            self.update()

    def create_address_group(self, title, data, color="blue200"):
        """host, port, address, type の入力セットを作成"""
        h_in = ft.TextField(label="Host", value=data.get("host", "localhost"), expand=2, dense=True)
        p_in = ft.TextField(label="Port", value=str(data.get("port", 15020)), expand=1, dense=True)
        a_in = ft.TextField(label="Addr", value=str(data.get("address", 0)), expand=1, dense=True)
        t_in = ft.Dropdown(
            label="Type", value=data.get("type", "coil"), expand=1, dense=True,
            options=[ft.dropdown.Option("coil"), ft.dropdown.Option("discrete"), ft.dropdown.Option("hr")]
        )
        
        ui = ft.Container(
            padding=10, bgcolor="white10", border_radius=8, border=ft.border.all(1, "white10"),
            content=ft.Column([
                ft.Text(title, size=12, weight="bold", color=color),
                ft.Row([h_in, p_in, a_in, t_in], spacing=10)
            ], spacing=5)
        )
        ui.data = {"host": h_in, "port": p_in, "address": a_in, "type": t_in}
        return ui

    def create_action_row(self, data, parent_list):
        """Action（演算）の1行分を作成"""
        h_in = ft.TextField(label="Host", value=data.get("host", "localhost"), expand=2, dense=True)
        p_in = ft.TextField(label="Port", value=str(data.get("port", 15020)), expand=1, dense=True)
        a_in = ft.TextField(label="Addr", value=str(data.get("address", 100)), expand=1, dense=True)
        op_in = ft.Dropdown(
            label="Op", value=data.get("op", "increment"), expand=2, dense=True,
            options=[
                ft.dropdown.Option("set"),
                ft.dropdown.Option("increment"),
                ft.dropdown.Option("add"),
                ft.dropdown.Option("decrement"),
            ]
        )
        v_in = ft.TextField(label="Val", value=str(data.get("value", 1)), expand=1, dense=True)

        row = ft.Row([
            h_in, p_in, a_in, op_in, v_in,
            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="red400", 
                          on_click=lambda _: (parent_list.controls.remove(row), self.update()))
        ], spacing=10)
        
        row.data = {"host": h_in, "port": p_in, "address": a_in, "op": op_in, "value": v_in}
        return row

    def create_connection_card(self, data):
        name_in = ft.TextField(label="Connection Name", value=data.get("name", "New Connection"), expand=True, dense=True, text_style=ft.TextStyle(weight="bold"))
        
        # 1. Trigger (上)
        trigger_ui = self.create_address_group("▲ TRIGGER (Source / Monitor)", data.get("trigger", {}), "blue200")
        
        # 2. Target (下)
        target_ui = self.create_address_group("▼ TARGET (Destination / Write)", data.get("target", {}), "green200")

        # 3. Actions (下)
        actions_list = ft.Column(spacing=5)
        def add_action_ui(act_data):
            actions_list.controls.append(self.create_action_row(act_data, actions_list))
            self.update()

        for act in data.get("actions", []):
            add_action_ui(act)

        actions_section = ft.Container(
            padding=10, bgcolor="white10", border_radius=8, border=ft.border.all(1, "white10"),
            content=ft.Column([
                ft.Row([
                    ft.Text("⚡ ACTIONS (On Trigger Rising Edge)", size=12, weight="bold", color="orange200"),
                    ft.TextButton("Add Action", icon=ft.Icons.ADD, on_click=lambda _: add_action_ui({}))
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                actions_list
            ], spacing=5)
        )

        card = ft.Container(
            bgcolor="#25282d", padding=20, border_radius=12, border=ft.border.all(1, "white24"),
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.LINK, color="orange400"),
                    name_in,
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="red400", on_click=lambda _: self.delete_connection(card))
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                
                ft.Column([
                    trigger_ui,
                    ft.Container(content=ft.Icon(ft.Icons.ARROW_DOWNWARD, color="white24", size=20), alignment=ft.Alignment.CENTER),
                    target_ui,
                    ft.Divider(height=10, color="transparent"),
                    actions_section
                ], spacing=0)
            ], spacing=15)
        )
        
        card.data = {"name_in": name_in, "trigger_ui": trigger_ui, "target_ui": target_ui, "actions_list": actions_list}
        return card

    def add_connection_ui(self, e):
        self.conn_column.controls.append(self.create_connection_card({}))
        self.update()

    def delete_connection(self, card):
        self.conn_column.controls.remove(card)
        self.update()

    async def handle_pick_directory(self, e=None):
        path = await ft.FilePicker().get_directory_path()
        if path:
            self.log_dir_field.value = path
            self.update()

    def save_settings(self, e):
        try:
            old_name = self.svc.get("name")
            new_name = self.name_field.value

            if old_name != new_name:
                rename_entity(self.app_state, "device", old_name, new_name)
                self.svc["name"] = new_name


            self.svc["cycle_ms"] = int(self.cycle_field.value)
            self.svc["log_dir"] = self.log_dir_field.value
            self.app_state.dirty = True


            new_conns = []
            for card in self.conn_column.controls:
                d = card.data
                t_d = d["trigger_ui"].data
                tar_d = d["target_ui"].data
                
                conn = {
                    "name": d["name_in"].value,
                    "trigger": {
                        "host": t_d["host"].value,
                        "port": int(t_d["port"].value),
                        "address": int(t_d["address"].value),
                        "type": t_d["type"].value
                    }
                }

                # Target (常に取得。もし空にしたい仕様なら、ここでアドレス判定などを入れる)
                conn["target"] = {
                    "host": tar_d["host"].value,
                    "port": int(tar_d["port"].value),
                    "address": int(tar_d["address"].value),
                    "type": tar_d["type"].value
                }

                # Actions
                actions = []
                for row in d["actions_list"].controls:
                    a_d = row.data
                    actions.append({
                        "host": a_d["host"].value,
                        "port": int(a_d["port"].value),
                        "address": int(a_d["address"].value),
                        "type": "hr",
                        "op": a_d["op"].value,
                        "value": int(a_d["value"].value)
                    })
                
                if actions:
                    conn["actions"] = actions
                
                new_conns.append(conn)
            
            self.svc["connections"] = new_conns
            self.on_back(f"IODevice '{self.svc['name']}' updated.")
        except Exception as ex:
            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red")
            self.app_page.snack_bar.open = True
            self.update()