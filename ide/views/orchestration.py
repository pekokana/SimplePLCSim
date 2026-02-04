import flet as ft
import yaml
import os
from models.config_manager import ConfigManager
from views.plc_editor import PlcEditorView

import copy
import difflib

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
        self.current_editing_svc = None # 現在編集中のデータを保持

        # --- 右側：設定パネル (最初は幅0で隠しておく) ---
        self.side_panel = ft.Container(
            content=ft.Text("Select a service to edit", color="white"),
            width=0, # 最初は隠す
            bgcolor="#25282d",
            padding=20,
            border_radius=10,
            animate=ft.Animation(500, ft.AnimationCurve.DECELERATE), # スライドのアニメーション
        )

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
        self.main_content = ft.Column([
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
                            ft.PopupMenuItem(content="Add Ladder", icon=ft.Icons.REORDER, on_click=lambda _: self.add_service("ladder")),
                            ft.PopupMenuItem(content="Add Device", icon=ft.Icons.SENSORS, on_click=lambda _: self.add_service("device")),
                            ft.PopupMenuItem(content="Add IO Device", icon=ft.Icons.HUB, on_click=lambda _: self.add_service("iodevice")),
                        ],
                        menu_position=ft.PopupMenuPosition.UNDER,
                        # ElevatedButtonの代わりに、見た目だけボタン風のContainerを使う
                        content=ft.Container(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.ADD, color="white", size=20),
                                    ft.Text("Add Service", color="white"),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=5,
                            ),
                            bgcolor=ft.Colors.BLUE_700,
                            padding=ft.padding.symmetric(horizontal=15, vertical=8),
                            border_radius=8,
                        ),
                    ),
                    ft.VerticalDivider(),
                    # --- 保存ボタン ---
                    ft.IconButton(
                        icon=ft.Icons.SAVE,
                        icon_color="blue400",
                        tooltip="Save Project (Overwrite)",
                        on_click=self.handle_save_project # 上書き保存
                    ),
                    ft.IconButton(
                        icon=ft.Icons.SAVE_AS,
                        icon_color="blue200",
                        tooltip="Save As...",
                        on_click=self.handle_save_as # 名前を付けて保存
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

        # --- 全体のレイアウトを Row に変更 ---
        self.content = ft.Row([
            self.main_content,
            self.side_panel
        ], expand=True, spacing=10)


    def delete_service(self, svc):
        self.app_state.config_data["services"].remove(svc)
        self.close_panel()
        self.load_yaml_and_build_ui()


    def close_panel(self):
        self.side_panel.width = 0
        self.side_panel.padding = 0
        self.update()

    def show_side_panel(self, svc):
        self.current_editing_svc = svc
        svc_type = svc.get("type", "unknown").lower()
        svc_name = svc.get("name", "")
        
        # --- 依存関係(depends_on)設定用のUI作成 ---
        # 自分以外のサービス名をリストアップ
        other_services = [
            s.get("name") for s in self.app_state.config_data.get("services", [])
            if s.get("name") != svc_name
        ]

        # 現在設定されている依存先を取得
        current_deps = svc.get("depends_on", [])
        
        # チェックボックスのリストを作成
        dep_checkboxes = []
        for name in other_services:
            dep_checkboxes.append(
                ft.Checkbox(label=name, value=(name in current_deps))
            )

        # 依存関係セクションのコンポーネント
        depends_section = ft.Column([
            ft.Text("Depends On (Startup Order)", weight="bold"),
            *dep_checkboxes
        ], spacing=0)

        # --- 共通項目 ---
        name_input = ft.TextField(
            label="Service Name", 
            value=svc.get("name", ""),
            # フォームを少しスッキリさせるために border_radius を調整
            border_radius=8
        )
        
        # --- タイプ別の動的項目 ---
        extra_controls = []
        
        if svc_type == "plc":
            port_input = ft.TextField(label="Modbus Port", value=str(svc.get("port", "15020")), border_radius=8)
            ladder_options = [
                ft.dropdown.Option(s.get("name")) 
                for s in self.app_state.config_data.get("services", []) 
                if s.get("type") == "ladder"
            ]
            ladder_select = ft.Dropdown(
                label="Linked Ladder", 
                options=ladder_options, 
                value=svc.get("ladder_link"),
                border_radius=8
            )
            extra_controls.extend([port_input, ladder_select])

        elif svc_type == "ladder":
            cycle_input = ft.TextField(
                label="Scan Cycle (ms)", 
                value=str(svc.get("scan_cycle_ms", "100")), 
                suffix=ft.Text("ms"),
                border_radius=8
            )
            extra_controls.append(cycle_input)

        elif svc_type == "device":
            plc_host = ft.TextField(label="PLC Host", value=svc.get("plc_host", "localhost"), border_radius=8)
            cycle_ms = ft.TextField(
                label="Update Cycle (ms)", 
                value=str(svc.get("cycle_ms", "100")), 
                suffix=ft.Text("ms"),
                border_radius=8
            )
            extra_controls.extend([plc_host, cycle_ms])

        # --- 保存(Apply)ロジック ---
        def apply_changes(e):
            old_name = svc.get("name")
            new_name = name_input.value.strip()

            if not new_name:
                self.app_page.snack_bar = ft.SnackBar(ft.Text("Service name cannot be empty"), bgcolor="red")
                self.app_page.snack_bar.open = True
                self.app_page.update()
                return

            # --- 重複チェック ---
            for s in self.app_state.config_data.get("services", []):
                if s is not svc and s.get("name") == new_name:
                    self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Service name '{new_name}' already exists"), bgcolor="red")
                    self.app_page.snack_bar.open = True
                    self.app_page.update()
                    return

            # --- services 側の名前更新 ---
            svc["name"] = new_name

            # --- project_files 側のキー追従 ---
            if old_name != new_name:
                pf = self.app_state.project_files.get(svc_type, {})
                if old_name in pf:
                    pf[new_name] = pf.pop(old_name)
                    pf[new_name]["name"] = new_name

                # --- args (YAMLファイル名) も追従 ---
                args = svc.get("args", [])
                if args:
                    old_file = args[0]
                    # plc_xxx.yaml → plc_newname.yaml 形式を想定
                    base, ext = os.path.splitext(old_file)
                    prefix = base.split("_", 1)[0]
                    new_file = f"{prefix}_{new_name}{ext}"
                    args[0] = new_file

            self.app_state.dirty = True


            # チェックされた項目だけを depends_on リストに格納
            svc["depends_on"] = [
                cb.label for cb in dep_checkboxes if cb.value
            ]

            if svc_type == "plc":
                svc["port"] = port_input.value
                svc["ladder_link"] = ladder_select.value
            elif svc_type == "ladder":
                svc["scan_cycle_ms"] = cycle_input.value
            elif svc_type == "device":
                svc["plc_host"] = plc_host.value
                svc["cycle_ms"] = cycle_ms.value
            
            self.close_panel()
            self.load_yaml_and_build_ui()

        # --- パネル構築 (PaddingとScrollの追加) ---
        # Containerで包むことで左右に 20px の余白を作ります
        self.side_panel.content = ft.Container(
            padding=ft.padding.all(20), # 上下左右すべてに20pxの余白
            content=ft.Column([
                # ヘッダー部分
                ft.Row([
                    ft.Text(f"{svc_type.upper()} Settings", size=20, weight="bold", color="white"),
                    ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: self.close_panel(), icon_color="white54")
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                
                ft.Divider(height=10, color="white24"),
                
                # 入力フィールド群
                name_input,
                *extra_controls,
                
                # ボタン配置
                ft.VerticalDivider(color="transparent"),
                ft.Text("Depends On (Startup Order)", size=14, weight="bold", color="blue200"),
                ft.Column(dep_checkboxes, spacing=0),
                ft.Divider(color="white24"),
                ft.ElevatedButton(
                    "Open Detailed Editor", 
                    icon=ft.Icons.OPEN_IN_NEW, 
                    on_click=lambda _: self.go_to_detail(svc), 
                    width=float("inf"),
                    style=ft.ButtonStyle(bgcolor="blue700", color="white", shape=ft.RoundedRectangleBorder(radius=8))
                ),
                ft.OutlinedButton(
                    "OK (Apply)", 
                    icon=ft.Icons.CHECK, 
                    on_click=apply_changes, 
                    width=float("inf"),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
                ),
                
                # 削除ボタン
                ft.Divider(height=30, color="transparent"),
                ft.TextButton(
                    "Delete Service", 
                    icon=ft.Icons.DELETE_OUTLINE, 
                    on_click=lambda _: self.delete_service(svc), 
                    style=ft.ButtonStyle(color="red400")
                ),
            ], 
            spacing=10, 
            scroll=ft.ScrollMode.AUTO # 項目が増えてもスクロールできるようにする
            )
        )
        
        # 余白分を考慮して、パネル幅を少し広めに設定 (350 -> 380)
        self.side_panel.width = 380
        self.side_panel.padding = 20
        self.update()

    # --- 保存前diff 処理
    def _make_yaml_diff(self, before: dict, after: dict) -> str:
        before_txt = yaml.dump(before or {}, sort_keys=False, allow_unicode=True).splitlines(keepends=True)
        after_txt = yaml.dump(after or {}, sort_keys=False, allow_unicode=True).splitlines(keepends=True)
        return "".join(difflib.unified_diff(before_txt, after_txt, fromfile="before", tofile="after"))

    # --- 保存実行ロジック ---

    async def handle_save_project(self, e):
        before = copy.deepcopy(self.app_state.config_data)

        async def do_save():
            if not self.app_state.orchestration_file or self.app_state.orchestration_file == "Untitled":
                await self.handle_save_as(e)
            else:
                await self._execute_full_save(self.app_state.orchestration_file)

        diff_txt = self._make_yaml_diff(before, self.app_state.config_data)

        def on_confirm(_):
            self.app_page.dialog.open = False
            self.app_page.update()
            self.app_page.run_task(do_save)

        def on_cancel(_):
            self.app_page.dialog.open = False
            self.app_page.update()

        self.app_page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Save diff preview"),
            content=ft.Container(
                content=ft.Text(diff_txt or "No changes."),
                width=900,
                height=500,
                padding=10
            ),
            actions=[
                ft.TextButton("Cancel", on_click=on_cancel),
                ft.ElevatedButton("Save", on_click=on_confirm)
            ]
        )
        self.app_page.dialog.open = True
        self.app_page.update()



    async def handle_save_as(self, e):
        """FilePickerを使用して新しいパスで保存"""
        # FilePickerをページから取得（main.pyでページに登録されている前提）
        # もしくは、その場で作成して await するスタイル
        picker = ft.FilePicker()
        
        target_path = await picker.save_file(
            dialog_title="Save Orchestrator Project...",
            file_name="orchestrator.yaml",
            allowed_extensions=["yaml", "yml"]
        )
        
        if target_path:
            await self._execute_full_save(target_path)

    async def _execute_full_save(self, path):
        """AppStateのロジックを呼び出して物理ファイルに書き出す"""
        try:
            config = self.config_manager.config_data
            # 1. 最新の命名規則を取得
            naming_rules = config.get("naming", {
                "plc": "plc_{name}.yaml",
                "device": "dev_{name}.yaml",
                "iodevice": "io_{name}.yaml",
                "ladder": "ld_{name}.yaml"
            })
            engine_paths = config.get("engines", {})

            # 2. 実行パスの設定を反映
            engines = self.config_manager.config_data.get("engines", {})
            
            # 3. 重要：UI上の最新リストを AppState.nodes に同期する
            # 今のコードでは config_data["services"] にデータが入っているので、それを nodes にコピーします
            current_services = self.app_state.config_data.get("services", [])
            
            # 各サービスの command を最新のエンジンパスに更新
            for svc in current_services:
                svc_type = svc.get("type")
                if svc_type in engines and engines[svc_type]:
                    svc["command"] = engines[svc_type]

            # AppState側の「保存対象」をセット
            self.app_state.nodes = current_services

            # 4. AppState の保存メソッドを実行
            success, msg = self.app_state.save_all(path, naming_rules, engine_paths)

            if success:
                self.app_state.dirty = False

            # 5. 結果表示
            color = ft.Colors.GREEN_700 if success else ft.Colors.RED_700
            self.app_page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
            self.app_page.snack_bar.open = True
            
            # ファイルパスが変わった（Save Asなど）場合のためにUIをリフレッシュ
            self.load_yaml_and_build_ui()
            self.app_page.update()

        except Exception as ex:
            print(f"DEBUG: Save Error -> {ex}") # デバッグ用にコンソールにも出す
            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Save failed: {str(ex)}"), bgcolor="red")
            self.app_page.snack_bar.open = True
            self.app_page.update()


    def did_mount(self):
        self.load_yaml_and_build_ui()

    # def load_yaml_and_build_ui(self):
    #     self.list_view.controls.clear()
        
    #     # 1. 新規プロジェクト（ファイルがまだ存在しない）場合
    #     if not self.app_state.orchestration_file or not os.path.exists(self.app_state.orchestration_file):
    #         # 状態管理にある初期データを使ってUIを構築
    #         services = self.app_state.config_data.get("services", [])
    #         if not services:
    #             self.list_view.controls.append(
    #                 ft.Text("No services defined. Click '+' to add (TBD).", color="grey")
    #             )
    #         else:
    #             for svc in services:
    #                 self.list_view.controls.append(self.create_service_card(svc))
    #         self.update()
    #         return

    #     # 2. 既存ファイルがある場合（従来のロジック）
    #     try:
    #         with open(self.app_state.orchestration_file, "r", encoding="utf-8") as f:
    #             data = yaml.safe_load(f)
    #             # AppStateに反映させておく
    #             self.app_state.config_data = data 

    #         services = data.get("services", [])
    #         for svc in services:
    #             self.list_view.controls.append(self.create_service_card(svc))
    #     except Exception as e:
    #         self.list_view.controls.append(ft.Text(f"Error: {str(e)}", color="red"))

    #     self.update()

    def load_yaml_and_build_ui(self):
        self.list_view.controls.clear()
         
        # 既存ファイルの読み込み
        if self.app_state.orchestration_file and os.path.exists(str(self.app_state.orchestration_file)):
            try:
                with open(self.app_state.orchestration_file, "r", encoding="utf-8") as f:
                    file_data = yaml.safe_load(f) or {}

                # services は「未保存のメモリ状態」を優先
                if "services" not in self.app_state.config_data:
                    self.app_state.config_data["services"] = file_data.get("services", [])
                else:
                    # services 以外の設定だけ同期
                    for k, v in file_data.items():
                        if k != "services":
                            self.app_state.config_data[k] = v

            except Exception as e:
                print(f"[WARN] Failed to load orchestration yaml: {e}")

            # 個別YAMLをまとめて読み込み
            self.load_project_files()

        services = self.app_state.config_data.get("services", [])
        for svc in services:
            self.list_view.controls.append(self.create_service_card(svc))
         
        self.update()


    def load_project_files(self):
        """orchestrator.yaml から参照されている個別 YAML を全てメモリに読み込む"""
        # 初期化
        for k in self.app_state.project_files:
            self.app_state.project_files[k].clear()

        services = self.app_state.config_data.get("services", [])
        base_dir = os.path.dirname(str(self.app_state.orchestration_file))

        for svc in services:
            svc_type = svc.get("type")
            args = svc.get("args", [])

            if not svc_type or not args:
                continue

            yaml_path = os.path.join(base_dir, args[0])

            if os.path.exists(yaml_path):
                try:
                    with open(yaml_path, "r", encoding="utf-8") as f:
                        self.app_state.project_files[svc_type][svc["name"]] = yaml.safe_load(f)
                except Exception as e:
                    print(f"[WARN] Failed to load {yaml_path}: {e}")
                    self.app_state.project_files[svc_type][svc["name"]] = {}
            else:
                # ファイルが無い場合の空データ
                self.app_state.project_files[svc_type][svc["name"]] = {
                    "kind": svc_type,
                    "name": svc.get("name")
                }


    def add_service(self, svc_type):
        """新しいサービスをAppStateのデータ構造に追加してUIを再構築"""
        new_svc = {
            "name": f"new_{svc_type}_{len(self.app_state.config_data.get('services', [])) + 1}",
            "type": svc_type,
            "image": f"simpleplcsim/{svc_type}:latest", # デフォルトイメージ
            "networks": ["plc_net"]
        }


        # --- サービス種別ごとの最低限スケルトンをメモリに作る ---
        svc_name = new_svc["name"]
        if svc_type == "plc":
            self.app_state.project_files["plc"][svc_name] = {
                "kind": "plc",
                "name": svc_name,
                "ports": [],
                "registers": [],
                "coils": []
            }
        elif svc_type == "device":
            self.app_state.project_files["device"][svc_name] = {
                "kind": "device",
                "name": svc_name,
                "register_map": []
            }
        elif svc_type == "iodevice":
            self.app_state.project_files["iodevice"][svc_name] = {
                "kind": "iodevice",
                "name": svc_name,
                "io": []
            }
        elif svc_type == "ladder":
            self.app_state.project_files["ladder"][svc_name] = {
                "kind": "ladder",
                "name": svc_name,
                "rungs": []
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
            "ladder": (ft.Icons.REORDER, "purple400"),
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
                    # on_click=lambda e, name=svc_name: print(f"Settings for {name}")
                    on_click=lambda e, s=svc: self.show_side_panel(s)
                ),
            )
        )


    def start_all(self, e):
        print("Starting all services...")

    def stop_all(self, e):
        print("Stopping all services...")

    def go_to_detail(self, svc):
        """詳細エディタ画面へ遷移するロジック"""
        if self.app_state.dirty:
            def do_go(_):
                self.app_page.dialog.open = False
                self._open_detail(svc)

            def do_cancel(_):
                self.app_page.dialog.open = False
                self.app_page.update()

            self.app_page.dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Unsaved changes"),
                content=ft.Text("You have unsaved changes. Continue without saving?"),
                actions=[
                    ft.TextButton("Cancel", on_click=do_cancel),
                    ft.ElevatedButton("Continue", on_click=do_go)
                ]
            )
            self.app_page.dialog.open = True
            self.app_page.update()
            return

        self._open_detail(svc)

    def sync_plc_summary_from_detail(self, plc_yaml: dict):
        """PLC詳細設計の内容を services 側の概要情報へ反映"""
        if not plc_yaml:
            return

        plc_name = plc_yaml.get("name")
        if not plc_name:
            return

        for svc in self.app_state.config_data.get("services", []):
            if svc.get("type") == "plc" and svc.get("name") == plc_name:
                # Orchestrator側に持たせたい要約情報を同期
                svc["name"] = plc_yaml.get("name", svc.get("name"))
                svc["port"] = plc_yaml.get("modbus", {}).get("port", svc.get("port"))

                # dirty を立てる
                self.app_state.dirty = True
                break


    def sync_device_summary_from_detail(self, dev_yaml: dict):
        if not dev_yaml:
            return
        name = dev_yaml.get("name")
        for svc in self.app_state.config_data.get("services", []):
            if svc.get("type") == "device" and svc.get("name") == name:
                svc["plc_host"] = dev_yaml.get("plc", {}).get("host", svc.get("plc_host"))
                svc["cycle_ms"] = dev_yaml.get("cycle_ms", svc.get("cycle_ms"))
                self.app_state.dirty = True
                break

    def sync_iodevice_summary_from_detail(self, io_yaml: dict):
        if not io_yaml:
            return
        name = io_yaml.get("name")
        for svc in self.app_state.config_data.get("services", []):
            if svc.get("type") == "iodevice" and svc.get("name") == name:
                svc["io_count"] = len(io_yaml.get("io", []))
                self.app_state.dirty = True
                break


    def _open_detail(self, svc):
        """詳細エディタ画面へ遷移するロジック"""
        svc_type = svc.get("type", "").lower()
        
        # サイドパネルを閉じる（広い画面で編集するため）
        self.close_panel()

        # 詳細画面から「戻る」ボタンが押された時の処理
        def on_back(message=None):
            # --- PLC詳細 → Orchestrator概要へ同期 ---
            if svc_type == "plc":
                plc_yaml = self.app_state.project_files["plc"].get(svc.get("name"))
                self.sync_plc_summary_from_detail(plc_yaml)
            # --- Device詳細 → Orchestrator概要へ同期 ---
            elif svc_type == "device":
                dev_yaml = self.app_state.project_files["device"].get(svc.get("name"))
                self.sync_device_summary_from_detail(dev_yaml)
            # --- iodevice詳細 → Orchestrator概要へ同期 ---
            elif svc_type == "iodevice":
                io_yaml = self.app_state.project_files["iodevice"].get(svc.get("name"))
                self.sync_iodevice_summary_from_detail(io_yaml)


            # メインコンテンツを元のリスト表示に戻す
            self.content.controls[0] = self.main_content
            self.load_yaml_and_build_ui() # 最新の状態を反映

            # 2. メッセージがあれば、戻った先の「今表示されているページ」でスナックバーを出す
            if message:
                self.app_page.snack_bar = ft.SnackBar(ft.Text(message), duration=2000)
                self.app_page.snack_bar.open = True

            self.update()

        # PLCタイプの場合、PlcEditorViewを表示
        if svc_type == "plc":
            plc_yaml = self.app_state.project_files["plc"].get(svc["name"])

            if plc_yaml is None:
                plc_yaml = {
                    "kind": "plc",
                    "name": svc["name"],
                    "ports": [],
                    "registers": [],
                    "coils": []
                }
                self.app_state.project_files["plc"][svc["name"]] = plc_yaml

            editor_view = PlcEditorView(
                page=self.app_page,
                state=self.app_state,
                svc=plc_yaml,
                on_back=on_back
            )

            # 現在のメインコンテンツ（リスト表示部分）をエディタに差し替え
            # self.content は [main_content, side_panel] の Row
            self.content.controls[0] = editor_view
            self.update()
        elif svc_type == "device":
            from views.device_editor import DeviceEditorView


            device_yaml = self.app_state.project_files["device"].get(svc["name"])


            if device_yaml is None:
                device_yaml = {
                    "kind": "device",
                    "name": svc["name"],
                    "register_map": []
                }
                self.app_state.project_files["device"][svc["name"]] = device_yaml


            editor_view = DeviceEditorView(
                page=self.app_page,
                state=self.app_state,
                svc=device_yaml,
                on_back=on_back
            )

            self.content.controls[0] = editor_view
            self.update()

        elif svc_type == "iodevice":
            from views.iodevice_editor import IoDeviceEditorView
            # editor_view = IoDeviceEditorView(
            #     page=self.app_page,
            #     state=self.app_state,
            #     svc=svc,
            #     on_back=on_back
            # )

            iodev_yaml = self.app_state.project_files["iodevice"].get(svc["name"])


            if iodev_yaml is None:
                iodev_yaml = {
                    "kind": "iodevice",
                    "name": svc["name"],
                    "io": []
                }
                self.app_state.project_files["iodevice"][svc["name"]] = iodev_yaml


            editor_view = IoDeviceEditorView(
                page=self.app_page,
                state=self.app_state,
                svc=iodev_yaml,
                on_back=on_back
            )

            self.content.controls[0] = editor_view
            self.update()
        else:
            # 他のタイプはまだ未実装のメッセージを出す
            self.app_page.snack_bar = ft.SnackBar(
                ft.Text(f"Editor for {svc_type.upper()} is coming soon!")
            )
            self.app_page.snack_bar.open = True
            self.app_page.update()
