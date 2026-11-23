"""Compilatore GDScript numerico -> C; ogni costrutto non riconosciuto è un errore."""
import ast
import re
from assets import ExportError

ACTION_KEYS = {'p1_jump': 1, 'jump': 1, 'ui_accept': 1, 'p1_attack': 2, 'attack': 2,
               'select': 4, 'pause': 8, 'ui_cancel': 8, 'start': 8,
               'p1_right': 16, 'right': 16, 'ui_right': 16, 'p1_left': 32, 'left': 32, 'ui_left': 32,
               'up': 64, 'ui_up': 64, 'down': 128, 'ui_down': 128, 'p1_switch': 256, 'switch': 256, 'r': 256, 'l': 512}
TYPES = {'float': 'float', 'int': 'int', 'bool': 'bool', 'Vector2': 'Vec2'}


class Script:
    def __init__(self, path, node, nodes, actions=None):
        self.path, self.node, self.nodes = path, node, nodes
        self.actions = actions or ACTION_KEYS
        self.variables = {}
        self.constants = set()
        self.locals = {}
        self.lines = path.read_text(encoding='utf-8-sig').splitlines()
        self.declarations, self.functions = [], {}
        self.line = 1

    def error(self, message):
        raise ExportError(self.path, self.line, message, 'GDS001')

    def node_reference(self, path):
        base = self.node['path']
        full = path if base == '.' else base + '/' + path
        for node in self.nodes:
            if node['path'] == full: return node['index']
        self.error('Nodo statico non trovato: $' + path)

    def expression(self, text):
        text = re.sub(r'\$([A-Za-z_][\w/]*)', lambda m: '__node_' + str(self.node_reference(m[1])), text)
        text = re.sub(r'\b(true|false)\b', lambda m: m[0].title(), text)
        try: tree = ast.parse(text, mode='eval').body
        except SyntaxError: self.error('Espressione non supportata: ' + text[:100])
        return self.expr(tree)

    def expr(self, node):
        if isinstance(node, ast.Constant):
            if type(node.value) is bool: return ('true' if node.value else 'false'), 'bool'
            if type(node.value) is int:
                if not -(2**30) <= node.value <= 2**30: self.error('Intero fuori intervallo C supportato')
                return str(node.value), 'int'
            if type(node.value) is float: return repr(node.value) + 'f', 'float'
            self.error('Stringhe ammesse solo nei nomi delle azioni Input')
        if isinstance(node, ast.Name):
            if node.id in self.locals: return 'v_' + node.id, self.locals[node.id]
            if node.id in self.variables: return f'n{self.node["index"]}_{node.id}', self.variables[node.id]
            if node.id == 'delta': return 'delta', 'float'
            if node.id in ('position', 'velocity'):
                if node.id=='velocity' and self.node['type']!='CharacterBody2D': self.error('velocity richiede CharacterBody2D')
                return f'nodes[{self.node["index"]}].' + node.id, 'Vector2'
            if node.id in ('frame', 'flip_h', 'flip_v', 'visible'):
                return f'nodes[{self.node["index"]}].{node.id}', 'int' if node.id == 'frame' else 'bool'
            self.error('Identificatore non convertibile: ' + node.id)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == 'Vector2' and node.attr == 'ZERO':
                return '(Vec2){0,0}', 'Vector2'
            if isinstance(node.value, ast.Name) and node.value.id.startswith('__node_'):
                index = int(node.value.id[7:])
                if node.attr not in ('frame', 'flip_h', 'flip_v', 'visible', 'position'): self.error('Proprietà nodo non supportata: ' + node.attr)
                if node.attr in ('frame','flip_h','flip_v') and self.nodes[index]['type'] != 'Sprite2D': self.error('Proprietà disponibile solo su Sprite2D')
                if self.nodes[index]['type']=='CollisionShape2D': self.error('CollisionShape2D non modificabile a runtime nel sottoinsieme GBA')
                return f'nodes[{index}].{node.attr}', 'Vector2' if node.attr == 'position' else 'int'
            value, kind = self.expr(node.value)
            if kind == 'Vector2' and node.attr in ('x', 'y'): return f'({value}).{node.attr}', 'float'
            self.error('Accesso a proprietà non supportato: ' + node.attr)
        if isinstance(node, ast.UnaryOp):
            value, kind = self.expr(node.operand)
            op = {ast.USub: '-', ast.UAdd: '+', ast.Not: '!'}.get(type(node.op))
            if not op or kind == 'Vector2': self.error('Operatore unario non supportato')
            return f'({op}({value}))', 'bool' if op == '!' else kind
        if isinstance(node, ast.BinOp):
            left, lt = self.expr(node.left); right, rt = self.expr(node.right)
            if 'Vector2' in (lt, rt):
                if lt == rt and isinstance(node.op, (ast.Add, ast.Sub)):
                    return f'gba_vec_{"add" if isinstance(node.op, ast.Add) else "sub"}({left},{right})', 'Vector2'
                if isinstance(node.op, ast.Mult) and (lt == 'Vector2') != (rt == 'Vector2'):
                    return f'gba_vec_scale({left if lt == "Vector2" else right},{right if lt == "Vector2" else left})', 'Vector2'
                self.error('Operazione Vector2 non supportata')
            op = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/', ast.Mod: '%'}.get(type(node.op))
            if op is None: self.error('Operatore aritmetico non supportato')
            kind = 'float' if 'float' in (lt, rt) else 'int'
            if op == '%' and kind != 'int': self.error('Modulo richiede interi')
            if op in ('/', '%'): return f'gba_{"divf" if kind == "float" else "divi" if op == "/" else "modi"}({left},{right})', kind
            return f'(({left}) {op} ({right}))', kind
        if isinstance(node, ast.BoolOp):
            values = [self.expr(v) for v in node.values]
            if any(t == 'Vector2' for _, t in values): self.error('Vector2 non utilizzabile come booleano')
            return '(' + (' && ' if isinstance(node.op, ast.And) else ' || ').join(v for v, _ in values) + ')', 'bool'
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            a, at = self.expr(node.left); b, bt = self.expr(node.comparators[0])
            op = {ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>='}.get(type(node.ops[0]))
            if not op or 'Vector2' in (at, bt): self.error('Confronto non supportato')
            return f'(({a}) {op} ({b}))', 'bool'
        if isinstance(node, ast.IfExp):
            c, ct = self.expr(node.test); a, at = self.expr(node.body); b, bt = self.expr(node.orelse)
            if ct == 'Vector2' or (at != bt and 'Vector2' in (at,bt)): self.error('Tipi incompatibili nella selezione')
            return f'(({c}) ? ({a}) : ({b}))', at
        if isinstance(node, ast.Call) and not node.keywords:
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                owner, name = node.func.value.id, node.func.attr
                if owner == 'Input':
                    if name not in ('is_action_pressed','is_action_just_pressed','get_axis'): self.error('Metodo Input non supportato: ' + name)
                    expected = 2 if name == 'get_axis' else 1
                    if len(node.args) != expected: self.error('Numero di azioni Input errato')
                    keys = []
                    for arg in node.args:
                        if not isinstance(arg, ast.Constant) or arg.value not in self.actions: self.error('Azione Input non mappata a un tasto GBA')
                        keys.append(str(self.actions[arg.value]))
                    if name == 'get_axis': return f'(gba_key_held({keys[1]}) - gba_key_held({keys[0]}))', 'float'
                    return f'{"gba_key_hit" if name.endswith("just_pressed") else "gba_key_held"}({keys[0]})', 'bool'
                if owner.startswith('__node_') and name == 'play' and not node.args:
                    index = int(owner[7:])
                    if self.nodes[index]['type'] != 'AudioStreamPlayer': self.error('play() richiede AudioStreamPlayer')
                    return f'play_sound({self.nodes[index]["sound"]}, {self.nodes[index]["volume"]})', 'void'
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name in ('move_and_slide','is_on_floor') and not node.args:
                    if self.node['type'] != 'CharacterBody2D': self.error(name + ' richiede CharacterBody2D')
                    return (f'move_body({self.node["index"]})', 'void') if name == 'move_and_slide' else (f'nodes[{self.node["index"]}].grounded', 'bool')
                args = [self.expr(a) for a in node.args]
                if name == 'Vector2' and len(args) == 2 and all(t != 'Vector2' for _,t in args): return '(Vec2){' + ','.join(v for v,_ in args) + '}', 'Vector2'
                functions = {'float': ('(float)',1,'float'), 'int': ('(int)',1,'int'), 'bool': ('(bool)',1,'bool'),
                             'absf': ('fabsf',1,'float'), 'minf': ('fminf',2,'float'), 'maxf': ('fmaxf',2,'float'),
                             'clampf': ('clamp_value',3,'float'), 'move_toward': ('approach',3,'float')}
                if name in functions:
                    cname, count, kind = functions[name]
                    if len(args) != count or any(t in ('Vector2','void') for _,t in args): self.error('Argomenti errati per ' + name)
                    return cname + '(' + ','.join(v for v,_ in args) + ')', kind
            self.error('Chiamata non convertibile: ' + ast.unparse(node.func))
        self.error('Costrutto non convertibile: ' + ast.unparse(node)[:120])

    def compile(self):
        function, stack, output = None, [], []
        for number, raw in enumerate(self.lines, 1):
            self.line = number
            # Commenti senza corrompere # dentro stringhe.
            text = re.split(r'#(?=(?:[^"\']|"[^"]*"|\'[^\']*\')*$)', raw, maxsplit=1)[0].strip()
            if not text: continue
            indent = len(raw.expandtabs(4)) - len(raw.expandtabs(4).lstrip())
            if indent == 0:
                if function:
                    output.extend('}' for _ in stack); stack=[]
                    self.functions[function] = '\n'.join(output)
                    function = None
                if text.startswith('extends '):
                    if text[8:] != self.node['type']: self.error('extends deve coincidere con il tipo del nodo statico')
                    continue
                if re.fullmatch(r'class_name [A-Za-z_]\w*', text): continue
                match = re.fullmatch(r'func (_ready|_physics_process)\((.*?)\) -> void:', text)
                if match:
                    function = match[1]
                    if function in self.functions: self.error('Funzione duplicata')
                    if match[2] != ('delta: float' if function == '_physics_process' else ''): self.error('Firma callback non supportata')
                    output, self.locals = [], {}
                    continue
                decl = re.fullmatch(r'(var|const) (\w+): (\w+)\s*=\s*(.+)', text)
                if decl:
                    storage, name, kind, value = decl.groups()
                    if kind not in TYPES: self.error('Tipo non convertibile: ' + kind)
                    if name in self.variables or name in ('position','velocity','frame','delta'): self.error('Nome variabile duplicato o riservato: ' + name)
                    code, actual = self.expression(value)
                    if actual == 'void' or ((kind == 'Vector2') != (actual == 'Vector2')): self.error('Tipo inizializzatore incompatibile')
                    # I globali C richiedono valori costanti; niente Input o accessi ai nodi nell'inizializzatore.
                    if re.search(r'\b(nodes|key_|n\d+_|delta|gba_)', code): self.error('Inizializzatore globale deve essere costante')
                    self.variables[name] = kind
                    if storage=='const': self.constants.add(name)
                    self.declarations.append(f'#line {number} "{self.path.as_posix()}"\nstatic {"const " if storage=="const" else ""}{TYPES[kind]} n{self.node["index"]}_{name} = {code};')
                    continue
                self.error('Dichiarazione non convertibile: ' + text[:110])
            if function is None: self.error('Istruzione fuori da una callback supportata')
            if indent % 4: self.error('Usare tab o indentazione di quattro spazi')
            while stack and indent <= stack[-1]: output.append('}'); stack.pop()
            expected = stack[-1] + 4 if stack else 4
            if indent != expected: self.error('Indentazione o blocco non valido')
            output.append(f'#line {number} "{str(self.path).replace(chr(92), "/")}"')
            if text.startswith(('if ', 'elif ')) and text.endswith(':'):
                branch = 'else if' if text.startswith('elif ') else 'if'
                expr = text[5:-1] if branch == 'else if' else text[3:-1]
                code, kind = self.expression(expr)
                if kind in ('Vector2','void'): self.error('Condizione non scalare')
                output.append(f'{branch} ({code}) {{'); stack.append(indent); continue
            if text == 'else:': output.append('else {'); stack.append(indent); continue
            if text == 'return': output.append('return;'); continue
            decl = re.fullmatch(r'var (\w+): (\w+)\s*=\s*(.+)', text)
            if decl:
                name, kind, value = decl.groups()
                if kind not in TYPES or name in self.locals or name in self.variables: self.error('Variabile locale non valida')
                code, actual = self.expression(value)
                if actual == 'void' or ((kind == 'Vector2') != (actual == 'Vector2')): self.error('Tipo locale incompatibile')
                self.locals[name] = kind
                output.append(f'{TYPES[kind]} v_{name} = {code}; (void)v_{name};'); continue
            assign = re.fullmatch(r'(.+?)\s*(\+=|-=|\*=|/=|=(?!=))\s*(.+)', text)
            if assign:
                lhs, op, rhs = assign.groups()
                if not re.fullmatch(r'(?:\$[A-Za-z_]\w*(?:/[A-Za-z_]\w*)*\.)?[A-Za-z_]\w*(?:\.[xy])?', lhs.strip()): self.error('Destinazione assegnamento non supportata')
                if lhs.strip().split('.')[0] in self.constants or lhs.strip()=='delta': self.error('Assegnamento a costante/parametro non supportato')
                a, at = self.expression(lhs.strip()); b, bt = self.expression(rhs)
                if bt == 'void' or ((at == 'Vector2') != (bt == 'Vector2')): self.error('Tipi incompatibili nell’assegnamento')
                if op != '=' and at == 'Vector2': self.error('Usare assegnamento Vector2 esplicito')
                if op == '/=': self.error('Usare divisione esplicita con controllo del divisore')
                output.append(f'{a} {op} {b};'); continue
            code, kind = self.expression(text)
            if kind != 'void': self.error('Espressione senza effetto non supportata')
            output.append(code + ';')
        if function:
            output.extend('}' for _ in stack)
            self.functions[function] = '\n'.join(output)
        return self.declarations, self.functions
