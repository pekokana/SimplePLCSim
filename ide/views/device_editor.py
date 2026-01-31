import flet as ft

class DeviceEditorView(ft.Container):
    def __init__(self, page: ft.Page, state, svc, on_back):
        super().__init__(expand=True, padding=30, bgcolor="#1a1c1e")
        self.app_page = page
        self.app_state = state
        self.svc = svc
        self.on_back = on_back

        # --- 基本設定用フィールド ---
        self.name_field = ft.TextField(label="Device Name", value=svc.get("name", ""), border_radius=8)
        self.log_dir_field = ft.TextField(label="Log Directory", value=svc.get("log_dir", "logs"), border_radius=8, read_only=True, expand=True)
        
        plc_cfg = svc.get("plc", {})
        self.host_field = ft.TextField(label="PLC Host", value=plc_cfg.get("host", "localhost"), width=200, border_radius=8)
        self.port_field = ft.TextField(label="Modbus Port", value=str(plc_cfg.get("port", 15021)), width=150, border_radius=8)
        self.cycle_field = ft.TextField(label="Cycle (ms)", value=str(svc.get("cycle_ms", 100)), width=150, border_radius=8, suffix="ms")
        self.heartbeat_offset_field = ft.TextField(label="PLC Heartbeat Offset", value=str(plc_cfg.get("heartbeat_offset", 512)), width=150, border_radius=8)

        # --- 信号リスト表示エリア ---
        self.signals_column = ft.Column(spacing=20, scroll=ft.ScrollMode.AUTO, expand=True)
        
        # 初期ロード時は update を行わない (RuntimeError回避)
        self.load_signals(do_update=False)

        self.content = ft.Column([
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.on_back(), icon_color="white54"),
                ft.Icon(ft.Icons.SENSORS, color="green400", size=30),
                ft.Text("Device Simulation Editor", size=24, weight="bold"),
            ], spacing=20),

            ft.Divider(height=20, color="white24"),

            ft.Row([
                ft.Column([
                    self.create_section_title("Connection & General"),
                    self.name_field,
                    ft.Row([self.log_dir_field, ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=lambda _: self.app_page.run_task(self.handle_pick_directory))]),
                    self.host_field,
                    self.port_field,
                    self.cycle_field,
                    self.heartbeat_offset_field,
                    ft.Divider(height=30, color="transparent"),
                    ft.ElevatedButton("Apply Changes", icon=ft.Icons.CHECK, on_click=self.save_settings, bgcolor="blue700", width=300, height=50),
                ], width=350, spacing=15),

                ft.VerticalDivider(width=1),
                
                ft.Column([
                    ft.Row([
                        self.create_section_title("Signals & Patterns"),
                        ft.ElevatedButton("Add Signal", icon=ft.Icons.ADD, on_click=self.add_signal_ui)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    self.signals_column
                ], expand=True)
            ], expand=True, alignment=ft.CrossAxisAlignment.START)
        ])

    def create_section_title(self, text):
        return ft.Text(text, size=16, weight="bold", color="green400")

    async def handle_pick_directory(self, e=None):
        path = await ft.FilePicker().get_directory_path(dialog_title="Select Log Directory")
        if path:
            self.log_dir_field.value = path
            self.update()

    def load_signals(self, do_update=True):
        self.signals_column.controls.clear()
        signals = self.svc.get("signals", {})
        for sig_name, sig_data in signals.items():
            self.signals_column.controls.append(self.create_signal_card(sig_name, sig_data))
        if do_update:
            self.update()

    def create_signal_card(self, name, data):

        # カード内の入力を保持するプロパティを独自に追加（回収用）
        name_tf = ft.TextField(label="Signal Name", value=name, width=200, dense=True)
        def on_type_change(e):
            sig_type = type_dd.value

            # 現在のpattern値を退避
            old_patterns = []
            for row in pattern_col.controls:
                v_tf, d_tf = row.data
                old_patterns.append((v_tf.value, d_tf.value))

            # UIを全消し
            pattern_col.controls.clear()

            # 新しい型で再生成
            for v, d in old_patterns:
                add_pattern_row(v, d, sig_type)

            self.update()

        type_dd = ft.Dropdown(
            label="Type", width=150, dense=True,
            value=data.get("type", "discrete"),
            options=[ft.dropdown.Option("discrete"), ft.dropdown.Option("coil"), ft.dropdown.Option("register")],
            # on_change=on_type_change
            on_text_change=on_type_change
        )
        addr_tf = ft.TextField(label="Addr", value=str(data.get("address", 0)), width=80, dense=True)
        pattern_col = ft.Column(spacing=5)

        # タイムライン表示制御
        timeline_row = ft.Row(spacing=4, wrap=True)
        def refresh_timeline():
            timeline_row.controls.clear()

            for row in pattern_col.controls:
                v_tf, d_tf = row.data
                try:
                    dur = int(d_tf.value)
                except:
                    dur = 0

                # 表示用幅（durationをスケーリング）
                width = max(20, min(dur // 50, 200))

                if type_dd.value in ("discrete", "coil"):
                    color = "green" if v_tf.value == "true" else "red"
                    label = v_tf.value
                else:
                    color = "blue"
                    label = v_tf.value

                timeline_row.controls.append(
                    ft.Container(
                        width=width,
                        height=24,
                        bgcolor=color,
                        border_radius=6,
                        tooltip=f"value={label}, duration={dur}ms",
                        content=ft.Text(label, size=10, color="white", text_align="center")
                    )
                )

            self.update()

        def add_pattern_row(val="true", dur=1000, sig_type="discrete"):
            if sig_type in ("discrete", "coil"):
                v_in = ft.Dropdown(
                    label="Value", width=150, dense=True,
                    value=val,
                    options=[ft.dropdown.Option("true"), ft.dropdown.Option("false")]
                )
            else:
                v_in = ft.TextField(
                    label="Value (0-65535)",
                    width=150,
                    dense=True,
                    value=str(val),
                    input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]"),
                )

            def on_register_change(e):
                try:
                    v = int(v_in.value)
                    if not (0 <= v <= 65535):
                        v_in.error_text = "0～65535 の範囲で入力してください"
                    else:
                        v_in.error_text = None
                except:
                    v_in.error_text = "数値を入力してください"
                self.update()

            v_in.on_change = on_register_change

            d_in = ft.TextField(value=str(dur), width=100, dense=True, label="ms", suffix="ms")
            row = ft.Row([
                v_in, d_in,
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="red400", on_click=lambda _: (pattern_col.controls.remove(row), refresh_timeline()))
            ])
            # 後で値を回収しやすいようにTextFieldを参照として保持させる
            row.data = (v_in, d_in) 
            pattern_col.controls.append(row)
            refresh_timeline()

        for p in data.get("pattern", []):
            # 修正前
            # add_pattern_row(p.get("value"), p.get("duration_ms"))
            #
            # 修正後
            raw_val = p.get("value")
            # YAML(bool/int) -> UI(str)へ変換
            if isinstance(raw_val, bool):
                ui_val = "true" if raw_val else "false"
            else:
                ui_val = str(raw_val)
            add_pattern_row(ui_val, p.get("duration_ms"), data.get("type", "discrete"))

        def add_step_default():
            default_val = "true" if type_dd.value in ("discrete", "coil") else "0"
            add_pattern_row(default_val, 1000, type_dd.value)
            self.update()


        card = ft.Container(
            bgcolor="#25282d", padding=15, border_radius=10, border=ft.border.all(1, "white10"),
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.SENSORS_OFF if data.get("type") == "discrete" else ft.Icons.SETTINGS_INPUT_COMPONENT, color="blue200"),
                    name_tf, type_dd, addr_tf,
                    ft.IconButton(ft.Icons.DELETE, icon_color="red", on_click=lambda _: self.delete_signal_from_ui(card))
                ]),
                timeline_row,
                pattern_col,
                # ft.TextButton("Add Step", icon=ft.Icons.ADD_CIRCLE_OUTLINE, on_click=lambda _: (add_pattern_row("true", 1000, type_dd.value), self.update()))
                ft.TextButton("Add Step", icon=ft.Icons.ADD_CIRCLE_OUTLINE, on_click=lambda _: add_step_default())
            ])
        )


        # 回収用にメタデータを埋め込む
        card.data = {"name_tf": name_tf, "type_dd": type_dd, "addr_tf": addr_tf, "pattern_col": pattern_col}
        return card

    def add_signal_ui(self, e):
        # 画面に空のカードを追加
        new_data = {"type": "discrete", "address": 0, "pattern": [{"value": "False", "duration_ms": 1000}]}
        self.signals_column.controls.append(self.create_signal_card("new_signal", new_data))
        self.update()

    def delete_signal_from_ui(self, card_obj):
        self.signals_column.controls.remove(card_obj)
        self.update()

    def save_settings(self, e):
        try:
            # 1. 基本設定の回収
            self.svc["name"] = self.name_field.value
            self.svc["log_dir"] = self.log_dir_field.value
            self.svc["plc"] = {"host": self.host_field.value, "port": int(self.port_field.value), "heartbeat_offset": int(self.heartbeat_offset_field)}
            self.svc["cycle_ms"] = int(self.cycle_field.value)

            # 2. シグナル情報の全回収
            new_signals = {}
            for card in self.signals_column.controls:
                d = card.data
                s_name = d["name_tf"].value
                s_type = d["type_dd"].value
                s_addr = int(d["addr_tf"].value)
                
                # パターンの回収
                patterns = []
                for row in d["pattern_col"].controls:
                    v_tf, d_tf = row.data
                    # bool値の変換 (discrete/coil用)
                    raw_val = v_tf.value.lower()
                    # val = True if raw_val == "true" else False if raw_val == "false" else int(v_tf.value)
                    if s_type in ("discrete", "coil"):
                        val = True if raw_val == "true" else False
                    else:
                        # val = int(raw_val)
                        iv = int(raw_val)
                        if not (0 <= iv <= 65535):
                            raise ValueError(f"Register value out of range: {iv}")
                        val = iv

                    patterns.append({
                        "value": val,
                        "duration_ms": int(d_tf.value)
                    })
                
                new_signals[s_name] = {
                    "type": s_type,
                    "address": s_addr,
                    "pattern": patterns
                }
            
            self.svc["signals"] = new_signals
            
            # 3. 完了通知付きで戻る
            self.on_back(f"Device '{self.svc['name']}' with {len(new_signals)} signals updated.")

        except Exception as ex:
            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Save Error: {str(ex)}"), bgcolor="red")
            self.app_page.snack_bar.open = True
            self.update()