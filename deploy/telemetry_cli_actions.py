"""Read fixed argparse command paths without importing a CLI or its handlers."""

from __future__ import annotations

import ast
import re


def command_names(source: str) -> set[str]:
    tree = ast.parse(source)
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    ]
    if len(functions) != 1:
        raise ValueError("Review the changed CLI entrypoint")
    main = functions[0]
    parents, groups, commands, namespaces, seen = {}, {}, set(), set(), set()

    def registration(node):
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"add_parser", "add_subparsers"}
        )

    expected = {id(node) for node in ast.walk(main) if registration(node)}

    def name(node, bindings):
        value = bindings.get(node.id) if isinstance(node, ast.Name) else ast.literal_eval(node)
        if type(value) is not str or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value):
            raise ValueError("Review the changed CLI command name")
        return value

    def walk(statements, bindings):
        for statement in statements:
            if isinstance(statement, ast.For) and any(registration(n) for n in ast.walk(statement)):
                if not isinstance(statement.target, ast.Name) or statement.orelse:
                    raise ValueError("Review the changed CLI declaration loop")
                values = ast.literal_eval(statement.iter)
                if type(values) not in {list, tuple} or not 1 <= len(values) <= 128:
                    raise ValueError("Review the changed CLI declaration loop")
                for value in values:
                    walk(statement.body, {**bindings, statement.target.id: value})
                continue
            if isinstance(statement, ast.If):
                walk(statement.body, bindings)
                walk(statement.orelse, bindings)
                continue
            target = None
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                if isinstance(statement.targets[0], ast.Name):
                    target = statement.targets[0].id
                call = statement.value
            elif isinstance(statement, ast.Expr):
                call = statement.value
            else:
                continue
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                continue
            receiver = call.func.value
            if (
                target
                and call.func.attr == "ArgumentParser"
                and isinstance(receiver, ast.Name)
                and receiver.id == "argparse"
            ):
                if parents:
                    raise ValueError("Review the changed CLI root parser")
                parents[target] = [()]
                continue
            if not registration(call):
                continue
            if not isinstance(receiver, ast.Name):
                raise ValueError("Review the changed CLI parser receiver")
            seen.add(id(call))
            if call.func.attr == "add_subparsers":
                if not target or receiver.id not in parents:
                    raise ValueError("Review the changed CLI parser hierarchy")
                groups[target] = parents[receiver.id]
                namespaces.update(parents[receiver.id])
                continue
            if receiver.id not in groups or len(call.args) != 1:
                raise ValueError("Review the changed CLI command declaration")
            names = [name(call.args[0], bindings)]
            for keyword in call.keywords:
                if keyword.arg is None:
                    raise ValueError("Review dynamic CLI parser options")
                if keyword.arg == "aliases":
                    if not isinstance(keyword.value, (ast.List, ast.Tuple)):
                        raise ValueError("Review dynamic CLI aliases")
                    names.extend(name(value, bindings) for value in keyword.value.elts)
            paths = [(*parent, value) for parent in groups[receiver.id] for value in names]
            if len(paths) != len(set(paths)) or any(path in commands for path in paths):
                raise ValueError("Duplicate CLI command declaration")
            commands.update(paths)
            if target:
                parents[target] = paths

    try:
        walk(main.body, {})
    except (TypeError, SyntaxError) as error:
        raise ValueError("Review the changed CLI command syntax") from error
    if seen != expected or not commands:
        raise ValueError("Review unrecognized CLI command declarations")
    return {" ".join(path) for path in commands - namespaces}
