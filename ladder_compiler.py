from ladder_parser import Lark_StandAlone, Transformer, Token

class LadderTransformer(Transformer):
    def _transform_device(self, item):
        """
        TokenまたはTokenを含むListを受け取り、'self.mem.X[10]' 形式の文字列を返す
        """
        # Larkがリスト [Token(...)] で渡してくる場合があるため、中身を取り出す
        target = item[0] if isinstance(item, list) and len(item) > 0 else item
        
        if isinstance(target, Token) and target.type == 'DEVICE':
            name = str(target)
            kind = name[0]
            addr = name[1:]
            return f"self.mem.{kind}[{addr}]"
        
        # すでに変換済みの文字列や、その他の場合はそのまま文字列化して返す
        return str(target)

    def device(self, token):
        return self._transform_device(token)

    def op_not(self, items):
        return f"(not {self._transform_device(items[0])})"
    
    def logic_and(self, items):
        parts = [self._transform_device(i) for i in items]
        return "(" + " and ".join(parts) + ")"
    
    def logic_or(self, items):
        parts = [self._transform_device(i) for i in items]
        return "(" + " or ".join(parts) + ")"

    def nested(self, items):
        # 括弧 [ ... ] の中身を処理
        return self._transform_device(items[0])

    def coil(self, items):
        return {"type": "COIL", "target": self._transform_device(items[0])}

    def res_inst(self, items):
        return {"type": "RES", "target": self._transform_device(items[0])}

    def timer_counter_inst(self, items):
        return {
            "type": str(items[0]),
            "target": self._transform_device(items[1]),
            "preset": int(items[2])
        }

    def out_sequence(self, items):
        # items[0] は現在の出力 (dict)
        # items[1] は次の out_sequence (list または None)
        res = [items[0]]
        if len(items) > 1 and items[1] is not None:
            next_items = items[1]
            if isinstance(next_items, list):
                res.extend(next_items)  # リストなら中身を追加
            else:
                res.append(next_items)  # 単体ならそのまま追加
        return res


    def standard_rung(self, items):
        # 最終的なロジック文字列をここで確定
        return {"logic": self._transform_device(items[0]), "outputs": items[1]}

    def end_rung(self, _):
        return {"type": "END"}

class LadderCompiler:
    def __init__(self):
        self.parser = Lark_StandAlone()
        self.transformer = LadderTransformer()

    def compile_line(self, line):
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        tree = self.parser.parse(line)
        return self.transformer.transform(tree)