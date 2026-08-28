"""Execute um arquivo SQL instrução a instrução em um SQL Warehouse."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def split_sql_statements(sql: str) -> list[str]:
    """Separe instruções por ponto e vírgula sem cortar strings ou comentários."""
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_backtick = False
    in_line_comment = False
    in_block_comment = False
    index = 0

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if in_line_comment:
            current.append(char)
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            current.append(char)
            if char == "*" and next_char == "/":
                current.append(next_char)
                index += 2
                in_block_comment = False
            else:
                index += 1
            continue

        if not (in_single_quote or in_double_quote or in_backtick):
            if char == "-" and next_char == "-":
                current.extend((char, next_char))
                index += 2
                in_line_comment = True
                continue
            if char == "/" and next_char == "*":
                current.extend((char, next_char))
                index += 2
                in_block_comment = True
                continue

        if char == "'" and not (in_double_quote or in_backtick):
            current.append(char)
            if in_single_quote and next_char == "'":
                current.append(next_char)
                index += 2
                continue
            in_single_quote = not in_single_quote
            index += 1
            continue

        if char == '"' and not (in_single_quote or in_backtick):
            in_double_quote = not in_double_quote
        elif char == "`" and not (in_single_quote or in_double_quote):
            in_backtick = not in_backtick

        if char == ";" and not (in_single_quote or in_double_quote or in_backtick):
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql_file", type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--warehouse-id", required=True)
    args = parser.parse_args()

    statements = split_sql_statements(args.sql_file.read_text(encoding="utf-8"))
    if not statements:
        parser.error("o arquivo SQL não contém instruções executáveis")

    for position, statement in enumerate(statements, start=1):
        summary = next((line.strip() for line in statement.splitlines() if line.strip()), "SQL")
        print(f"[{position}/{len(statements)}] {summary[:100]}", flush=True)
        result = subprocess.run(
            [
                "databricks",
                "experimental",
                "aitools",
                "tools",
                "query",
                "--warehouse",
                args.warehouse_id,
                "--profile",
                args.profile,
                "--output",
                "json",
                statement,
            ],
            check=False,
        )
        if result.returncode != 0:
            print(f"Execução interrompida na instrução {position}.", flush=True)
            return result.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
