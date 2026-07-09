#!/usr/bin/env python3
"""Adiciona URL adicional (atributo KP2A_URL*) a uma entrada KeePass.

O KeePassXC-Browser reconhece atributos com prefixo KP2A_URL como URLs
adicionais da entrada — mesmo mecanismo do campo "Additional URLs" da GUI.

Uso: add_extra_url.py <db_path> <entry_path> <url> [keyfile]
Senha master lida do stdin (nunca via argumento).
"""
import sys

from pykeepass import PyKeePass


def main():
    if len(sys.argv) < 4:
        print("uso: add_extra_url.py <db_path> <entry_path> <url> [keyfile]", file=sys.stderr)
        return 2
    db_path, entry_path, url = sys.argv[1:4]
    keyfile = sys.argv[4] if len(sys.argv) > 4 else None
    password = sys.stdin.readline().rstrip("\n")

    try:
        kp = PyKeePass(db_path, password=password, keyfile=keyfile)
    except Exception as e:
        print(f"erro ao abrir banco: {e}", file=sys.stderr)
        return 1

    parts = [p for p in entry_path.split("/") if p]
    entry = kp.find_entries(path=parts)
    if entry is None:
        print(f"entrada não encontrada: {entry_path}", file=sys.stderr)
        return 1

    existing = {k: v for k, v in entry.custom_properties.items() if k.startswith("KP2A_URL")}
    if url == entry.url or url in existing.values():
        print("URL já presente; nada a fazer.")
        return 0

    if "KP2A_URL" not in existing:
        key = "KP2A_URL"
    else:
        n = 1
        while f"KP2A_URL_{n}" in existing:
            n += 1
        key = f"KP2A_URL_{n}"

    entry.set_custom_property(key, url)
    kp.save()
    print(f"✓ {key} = {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
