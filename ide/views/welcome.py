import flet as ft


class WelcomeView(ft.Container):
    def __init__(self, page: ft.Page, state, on_project_loaded):
        super().__init__()
        # self.page = page  <-- これがエラーの原因。削除します。
        self.app_state = state  # ついでに他の変数名も整理
        self.on_project_loaded = on_project_loaded 
        self.expand = True
        
        # UI構築
        self.content = ft.Column([
            ft.Text("SimplePLCSim IDE", size=40, weight="bold"),
            ft.Text("オーケストレーション定義YAMLを選択して開始してください"),
            ft.ElevatedButton(
                "Open Orchestration YAML",
                icon=ft.Icons.FOLDER_OPEN,
                on_click=self.pick_file
            )
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    async def pick_file(self, e):
        self.file_picker = ft.FilePicker()
        # ファイル選択を実行
        result = await self.file_picker.pick_files(
            allowed_extensions=["yaml", "yml"],
            allow_multiple=False
        )
        if result:
            # result.files があればそれを、なければ result 自体（リスト）を使用
            files = getattr(result, "files", result)
            
            if files and len(files) > 0:
                # 取得したファイル（リストの最初の要素）のパスを取得
                # オブジェクトの場合は .path、辞書の場合は ["path"]
                file_path = files[0].path if hasattr(files[0], "path") else files[0]
                
                # 状態を更新
                self.app_state.set_project(file_path)
                # メイン側に通知して画面を切り替えてもらう
                await self.on_project_loaded()