#!/usr/bin/env python3
"""Lê ~/.claude/keepass-config.json sem depender de jq.

Uso:
  kp_config.py                  # todas as DBs: alias|path|service|account|keyfile
  kp_config.py --alias pessoal  # só uma DB (exit 1 se alias não existir)
  kp_config.py --aliases        # só os aliases, um por linha
  kp_config.py --validate       # valida o JSON (exit 0/1)

Saída pipe-delimited pra consumo em shell:
  while IFS='|' read -r alias path service account keyfile; do ... done
"""
import json
import os
import sys

CONFIG = os.path.expanduser("~/.claude/keepass-config.json")


def main() -> int:
    if not os.path.isfile(CONFIG):
        print(f"config não encontrado: {CONFIG}", file=sys.stderr)
        return 2
    try:
        with open(CONFIG) as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        print(f"JSON inválido: {e}", file=sys.stderr)
        return 1

    args = sys.argv[1:]
    if args[:1] == ["--validate"]:
        print("ok")
        return 0

    dbs = cfg.get("databases", [])
    if args[:1] == ["--aliases"]:
        for d in dbs:
            print(d["alias"])
        return 0

    if args[:1] == ["--alias"]:
        if len(args) < 2:
            print("uso: --alias <nome>", file=sys.stderr)
            return 2
        dbs = [d for d in dbs if d["alias"] == args[1]]
        if not dbs:
            print(f"alias '{args[1]}' não encontrado", file=sys.stderr)
            return 1

    for d in dbs:
        fields = (d["alias"], d["path"], d["keychain_service"],
                  d["keychain_account"], d.get("keyfile") or "")
        if any("|" in str(v) for v in fields):
            print(f"campo com '|' no alias {d['alias']}; corrija o config",
                  file=sys.stderr)
            return 1
        print("|".join(fields))
    return 0


if __name__ == "__main__":
    sys.exit(main())
