from enum import Enum

class ThemeColor(str, Enum):
    # メインカラー
    PRIMARY = "#005FB8"     # インダストリアル・ブルー
    PRIMARY_DARK = "#004A8F"
    SIMULATION = "#28A745"    # Simulationモード用（セーフティ・グリーン）
    
    # アクセント
    ACCENT = "#FFB900"      # コーション・イエロー
    
    # 背景
    BG_MAIN = "#1E1E1E"     # エディタ
    BG_SIDEBAR = "#252526"  # サイドバー

    # 背景(#1E1E1E)より少し明るいグレーを指定
    SURFACE = "#2D2D2D"

    # メモリ種別ごとの色（シミュレーターならでは！）
    MEM_X = "#4B9DEA"       # 入力：青
    MEM_Y = "#E67E22"       # 出力：オレンジ
    MEM_M = "#95A5A6"       # 内部：グレー
    MEM_D = "#27AE60"       # データ：グリーン
    
    # テキスト・状態
    TEXT_MAIN = "#D4D4D4"
    TEXT_ON_PRIMARY = "#FFFFFF" # 背景色の上の白文字
    SUCCESS = "#28A745"
    ERROR = "#D32F2F"

    # CARDの配色
    PLC_CARD = "#3E4A59"   # 少し青みがかったグレー
    DEVICE_CARD = "#4A593E" # 少し緑がかったグレー
    IO_CARD = "#593E3E"     # 少し赤みがかったグレー

    DND = "#444444" # ドラッグアンドドロップ