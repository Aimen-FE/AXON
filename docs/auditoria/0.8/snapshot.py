"""Exporta contratos declarados por la copia de AXON indicada en PYTHONPATH."""

import argparse
import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import app as app_package
from app.config import Settings
from app.db import Base
from app.main import create_app


def write_row(*fields):
    def cell(value):
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    print("\t".join(cell(value) for value in fields))


def capture_http(spec):
    write_row("method", "path", "operation", "parameters", "request_body", "success_responses")
    for path, entry in sorted(spec["paths"].items()):
        for method, operation in sorted(entry.items()):
            if method not in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}:
                continue
            responses = {code: response for code, response in operation["responses"].items()
                         if code.startswith("2")}
            parameters = entry.get("parameters", []) + operation.get("parameters", [])
            write_row(method.upper(), path, operation["operationId"], parameters,
                      operation.get("requestBody", {}), responses)


def capture_storage():
    write_row("table", "model_module", "columns", "primary_key", "foreign_keys")
    modules = {mapper.local_table.name: mapper.class_.__module__ for mapper in Base.registry.mappers}
    for name, table in sorted(Base.metadata.tables.items()):
        columns = [[col.name, str(col.type), col.nullable] for col in table.columns]
        references = sorted([fk.parent.name, fk.target_fullname, fk.ondelete or ""]
                            for fk in table.foreign_keys)
        write_row(name, modules.get(name, ""), columns, list(table.primary_key.columns.keys()), references)


def local_imports(nodes, module_names, own_name):
    found = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            names = [a.name.removeprefix("app.") for a in node.names if a.name.startswith("app.")]
        elif isinstance(node, ast.ImportFrom) and (node.level == 1 or node.module == "app"
                                                  or (node.module or "").startswith("app.")):
            if node.module in (None, "app"):
                names = [a.name for a in node.names]
            else:
                names = [node.module.removeprefix("app.")]
        else:
            continue
        found.update(name.split(".")[0] for name in names)
    return sorted((found & module_names) - {own_name})


def capture_imports():
    sources = sorted(Path(app_package.__file__).parent.glob("*.py"))
    module_names = {source.stem for source in sources}
    write_row("module", "top_level_imports", "all_static_imports")
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        write_row(source.stem, local_imports(tree.body, module_names, source.stem),
                  local_imports(ast.walk(tree), module_names, source.stem))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", choices=("http", "storage", "imports"))
    args = parser.parse_args()
    if args.inventory == "imports":
        capture_imports()
        return
    with TemporaryDirectory() as folder:
        settings = Settings(data_dir=Path(folder), database_url="sqlite:///:memory:", demo=False,
                            ai_mode="simulated", ollama_url="http://127.0.0.1:11434",
                            ollama_model="", ai_timeout=1, cookie_secure=False, allowed_origins=())
        app = create_app(settings, initialize=False, maintenance=False)
        try:
            if args.inventory == "http":
                capture_http(app.openapi())
            else:
                capture_storage()
        finally:
            app.state.engine.dispose()


if __name__ == "__main__":
    main()
