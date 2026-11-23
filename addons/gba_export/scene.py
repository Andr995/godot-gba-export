"""Parser TSCN strettamente dichiarativo: non carica né esegue GDScript."""
from dataclasses import dataclass, field
from pathlib import Path
import ast
import base64
import re
import struct
from assets import ExportError


@dataclass
class Call:
    name: str
    args: list


def literal(text, path, line):
    text = re.sub(r'\b(true|false|null)\b', lambda m: {'true': 'True', 'false': 'False', 'null': 'None'}[m[0]], text)
    text = re.sub(r'&(?=["\'])', '', text)
    try: tree = ast.parse(text, mode='eval').body
    except SyntaxError as exc: raise ExportError(path, line, 'Valore TSCN non supportato: ' + text[:90]) from exc
    def visit(node):
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, (ast.Tuple, ast.List)): return [visit(n) for n in node.elts]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = visit(node.operand)
            if not isinstance(value, (int, float)): raise ExportError(path, line, 'Segno su valore non numerico')
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            return Call(node.func.id, [visit(n) for n in node.args])
        raise ExportError(path, line, 'Espressione non dichiarativa nel TSCN')
    return visit(tree)


@dataclass
class Section:
    kind: str
    attrs: dict
    line: int
    props: dict = field(default_factory=dict)
    lines: dict = field(default_factory=dict)


def parse(path):
    sections, section = [], None
    lines = Path(path).read_text(encoding='utf-8-sig').splitlines()
    i = 0
    while i < len(lines):
        line_no = i + 1
        text = lines[i].strip()
        i += 1
        if not text or text.startswith(';'): continue
        if text.startswith('[') and text.endswith(']'):
            header = text[1:-1]
            kind = header.split()[0]
            rest = header[len(kind):]
            attrs = {}
            pattern = r'(\w+)=("(?:[^"\\]|\\.)*"|\w+\([^)]*\)|[^ ]+)'
            for match in re.finditer(pattern, rest):
                attrs[match[1]] = literal(match[2], path, line_no)
            if re.sub(pattern, '', rest).strip(): raise ExportError(path, line_no, 'Header TSCN non supportato')
            section = Section(kind, attrs, line_no)
            sections.append(section)
        elif section is not None and '=' in text:
            key, value = text.split('=', 1)
            # I valori Packed* possono occupare più righe. Il parser AST rileva la chiusura.
            while True:
                try:
                    parsed = literal(value.strip(), path, line_no)
                    break
                except ExportError:
                    if i >= len(lines) or lines[i].lstrip().startswith('['): raise
                    value += '\n' + lines[i]
                    i += 1
            key = key.strip()
            if key in section.props: raise ExportError(path, line_no, 'Proprietà TSCN duplicata: ' + key)
            section.props[key], section.lines[key] = parsed, line_no
        else: raise ExportError(path, line_no, 'Sintassi TSCN non supportata')
    if not sections or sections[0].kind != 'gd_scene': raise ExportError(path, 1, 'Richiesta scena testuale Godot 4 (.tscn)')
    return sections


def vector(value, path, line, name='Vector2'):
    if not isinstance(value, Call) or value.name not in (name, 'Vector2i') or len(value.args) != 2 or not all(isinstance(v, (float, int)) for v in value.args):
        raise ExportError(path, line, 'Richiesto ' + name + ' numerico')
    return value.args


def local_path(root, resource, origin, line):
    if not isinstance(resource, str) or not resource.startswith('res://'):
        raise ExportError(origin, line, 'Risorsa richiesta con percorso res:// esplicito')
    relative = Path(resource[6:])
    result = root / relative
    if not result.resolve().is_relative_to(root.resolve()):
        raise ExportError(origin, line, 'Risorsa esterna alla cartella di progetto')
    if not result.is_file(): raise ExportError(origin, line, 'Risorsa mancante: ' + resource)
    return result


def tile_cells(value, path, line):
    if not isinstance(value, Call) or value.name != 'PackedByteArray':
        raise ExportError(path, line, 'TileMapLayer richiede tile_map_data PackedByteArray')
    try:
        data = base64.b64decode(value.args[0], validate=True) if len(value.args) == 1 and isinstance(value.args[0], str) else bytes(value.args)
    except (ValueError, TypeError) as exc: raise ExportError(path, line, 'tile_map_data non valido') from exc
    if not data: return []
    if len(data) < 2 or struct.unpack_from('<H', data)[0] != 0 or (len(data) - 2) % 12:
        raise ExportError(path, line, 'Formato TileMapLayer sconosciuto/troncato; supportata versione 0 a celle di 12 byte')
    return list(struct.iter_unpack('<hhHHHH', data[2:]))
