"""Every production JSON boundary uses the one strict decoder."""
import ast
from pathlib import Path


CODE_ROOT=Path(__file__).resolve().parents[1]/'bdt'


def raw_json_decoders(root=CODE_ROOT):
    files=sorted(root.rglob('*.py'));violations=[]
    for path in files:
        if path.name=='json_codec.py':
            continue
        tree=ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
        json_names={'json'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                json_names.update(alias.asname or alias.name for alias in node.names if alias.name=='json')
            elif isinstance(node,ast.ImportFrom) and node.module=='json':
                for alias in node.names:
                    if alias.name in {'load','loads','*'}:
                        violations.append(f'{path.relative_to(root)}:{node.lineno}:json.{alias.name}')
        for node in ast.walk(tree):
            if (isinstance(node,ast.Attribute) and node.attr in {'load','loads'}
                    and isinstance(node.value,ast.Name) and node.value.id in json_names):
                violations.append(f'{path.relative_to(root)}:{node.lineno}:json.{node.attr}')
    return len(files),sorted(set(violations))


def test_production_json_boundaries_use_the_strict_decoder():
    scanned,violations=raw_json_decoders()
    assert not violations,f'scanned={scanned}; raw_json_decoders={len(violations)}; '+', '.join(violations)
