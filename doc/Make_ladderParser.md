1. larkファイルで構文定義を編集する
2. larkファイルを更新する
3. パーサーコードを書き出しする
   1. python -m lark.tools.standalone ladder.lark > ladder_parser.py
4. ladder_parser.pyが作成または更新されていることを確認する
5. ladder_compiler.pyの内容を対応させる
6. plcsim.pyでladder_compilerの読み込み