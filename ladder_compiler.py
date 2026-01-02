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

    # 比較演算 [ C0 < 100 ] の評価
    def op_compare(self, items):
        # items: [左辺, 演算子, 右辺]
        left = self._transform_device(items[0])
        op = str(items[1])
        # 右辺がデバイスならメモリ参照、数字ならそのまま
        right = self._transform_device(items[2]) if hasattr(items[2], 'type') and items[2].type == 'DEVICE' else str(items[2])
        return f"({left} {op} {right})"

    # 代入・計算命令 --(D0 = D1 + 1)
    def calc_inst(self, items):
        # items[0]はcalc_expr(文字列)
        return {"type": "CALC", "formula": items[0]}

    def calc_expr(self, items):
        # DEVICE "=" math_expr
        target = self._transform_device(items[0])
        expression = items[1]
        return f"{target} = {expression}"

    def math_expr(self, items):
        # term (OP term)*
        # items は [左辺, 演算子, 右辺, 演算子, ...] のリストになる
        res = []
        for i in items:
            if isinstance(i, Token) and i.type == 'OP':
                res.append(str(i))
            else:
                # term (DEVICE or NUMBER) を変換
                res.append(self._transform_device(i))
        return " ".join(res)

    def term(self, items):
        return items[0] # DEVICE or NUMBER

    def calc_inst(self, items):
        # items[0] は calc_expr で生成された文字列 "self.mem.D[0] = ..."
        return {"type": "CALC", "formula": items[0]}


    def op_math(self, items):
        # DEVICE "=" DEVICE OP DEVICE -> D0 = D1 + 10
        target = self._transform_device(items[0])
        left = self._transform_device(items[1])
        op = str(items[2])
        right = self._transform_device(items[3]) if hasattr(items[3], 'type') and items[3].type == 'DEVICE' else str(items[3])
        return f"{target} = {left} {op} {right}"

    def op_mov(self, items):
        # DEVICE "=" DEVICE -> D0 = D1
        target = self._transform_device(items[0])
        source = self._transform_device(items[1]) if hasattr(items[1], 'type') and items[1].type == 'DEVICE' else str(items[1])
        return f"{target} = {source}"

    def const_true(self, _): return "True"
    def const_false(self, _): return "False"

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