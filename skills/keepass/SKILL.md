---
name: keepass
description: "Use this skill when the user asks about passwords, credentials, logins, secrets, or KeePass entries. Supports multiple databases with Keychain authentication and optional .keyx key files. Database list is read from ~/.claude/keepass-config.json."
tags:
  - credentials
  - security
  - keepass
  - multi-database
---

# KeePass Skill — Multi-Database

Auto-loaded quando o usuário menciona passwords, credentials, logins, ou KeePass entries.

Suporta **N databases** configuradas em `~/.claude/keepass-config.json`, com autenticação via macOS Keychain e suporte a arquivos `.keyx`. Pesquisa global em todas as databases por padrão.

## Plataformas Suportadas

| OS | Suporte | Secret Store | Requisito |
|----|---------|--------------|-----------|
| macOS | ✅ Nativo | Keychain (`security`) | `keepassxc` via Homebrew |
| Linux | ✅ Nativo | libsecret (`secret-tool`) | `keepassxc` + `libsecret-tools` |
| Windows (WSL 2) | ✅ Via WSL | libsecret (`secret-tool`) | WSL 2 Ubuntu + mesmos do Linux |
| Windows (nativo) | ❌ Não suportado | — | — |

## Configuração

### Arquivo de configuração

```
~/.claude/keepass-config.json
```

Gerado pelo wizard `/keepass-setup`. Formato:

```json
{
  "databases": [
    {
      "alias": "alias-curto",
      "path": "/caminho/completo/para/banco.kdbx",
      "keychain_service": "keepassxc-cli",
      "keychain_account": "keepass-alias-curto",
      "keyfile": null
    },
    {
      "alias": "outro-banco",
      "path": "/caminho/para/outro.kdbx",
      "keychain_service": "keepassxc-cli",
      "keychain_account": "keepass-outro-banco",
      "keyfile": "/caminho/para/chave.keyx"
    }
  ]
}
```

Se o arquivo não existir, orientar o usuário a executar `/keepass-setup`.

## Quick Reference — Padrões de Busca

### Busca Global (padrão)

Percorre **todas** as databases configuradas:

```bash
CONFIG="$HOME/.claude/keepass-config.json"
KEEPASSXC=$(find_keepassxc_cli)

for alias in $(jq -r '.databases[].alias' "$CONFIG"); do
  db_info=$(jq ".databases[] | select(.alias == \"$alias\")" "$CONFIG")
  path=$(echo "$db_info" | jq -r '.path')
  account=$(echo "$db_info" | jq -r '.keychain_account')
  service=$(echo "$db_info" | jq -r '.keychain_service')
  keyfile=$(echo "$db_info" | jq -r '.keyfile // empty')

  # get_password abstrai Keychain (macOS) vs secret-tool (Linux/WSL)
  pass=$(get_password "$service" "$account")
  [ -z "$pass" ] && echo "❌ [$alias] Senha não encontrada no secret store" && continue

  if [ -n "$keyfile" ] && [ -f "$keyfile" ]; then
    result=$(echo "$pass" | "$KEEPASSXC" search -q -k "$keyfile" "$path" "TERMO" 2>&1)
  else
    result=$(echo "$pass" | "$KEEPASSXC" search -q "$path" "TERMO" 2>&1)
  fi

  [ -n "$result" ] && echo "$result" | sed "s/^/[$alias] /"
done
```

### Busca Filtrada

Se usuário especificar `--db <alias>`:

```bash
db_info=$(jq ".databases[] | select(.alias == \"$alias\")" "$CONFIG")
# ... processar apenas esse banco
```

## Padrões de Segurança

1. ✅ Sempre passar senha via **stdin pipe** — nunca expor na CLI, logs ou variáveis visíveis
2. ✅ Suportar arquivos `.keyx` com flag `-k` quando configurado
3. ✅ **Confirmar antes de `rm`** — perguntar explicitamente: "Confirma exclusão de 'X'? (s/n)"
4. ✅ **Verificar KeePassXC fechado** antes de writes: `pgrep -x KeePassXC`
5. ✅ **Validar `$pass` não-vazio** antes do pipe — erro claro se Keychain falhou
6. ✅ **Validar arquivo `.kdbx` existe** — `test -f "$path"` antes de qualquer op
7. ✅ **Avisar sobre texto claro** — `show` exibe senha sem encriptação
8. ✅ **Usar aspas duplas** — caminhos têm espaços; nunca `$path` sem aspas

## Tratamento de Erros Comuns

| Erro | Causa | OS | Ação |
|------|-------|----|------|
| `already locked` / `in use` | KeePassXC desktop aberto | Todos | Fechar app antes de writes |
| `Invalid credentials` / `Wrong key` | Senha master errada no secret store | Todos | Deletar e re-adicionar senha |
| Arquivo não encontrado | Nuvem não sincronizada | Todos | Aguardar sync ou abrir app de nuvem |
| Saída vazia | Nenhuma entrada encontrada | Todos | Normal — informar ao usuário |
| `jq: command not found` | `jq` não instalado | Todos | macOS: `brew install jq` / Linux: `sudo apt install jq` |
| `keepassxc-cli: command not found` | App não instalado | Todos | macOS: `brew install keepassxc` / Linux: `sudo apt install keepassxc` |
| `secret-tool: command not found` | libsecret não instalado | Linux/WSL | `sudo apt install libsecret-tools` |
| `Cannot autolaunch D-Bus` | Sem sessão D-Bus ativa | Linux/WSL headless | Executar em sessão desktop ou exportar `DBUS_SESSION_BUS_ADDRESS` |

## Quando Carrega Automaticamente

Este skill auto-carrega quando detecta:

- "qual é a senha de..." / "what's the password for..."
- "busca no KeePass..." / "search KeePass..."
- "mostra credenciais de..." / "show credentials..."
- "adiciona entrada..." / "add entry..."
- "qual o token/chave/secret para..."
- Qualquer menção a "password", "credential", "secret", "login", "api key", "token"

## Como Usar

### Natural Language (Skill Auto-Carrega)

```
Usuário: "qual a senha do GitHub?"

Claude:
1. Skill detecta pergunta sobre credencial
2. Lê lista de databases do config
3. Busca globalmente em todas as databases
4. Retorna resultado com username/URL (sem exibir senha)
5. Oferece: "Execute /keepass show 'Grupo/GitHub' para ver a senha"
```

### Comando Explícito

```
/keepass search github              # busca em TODAS as databases
/keepass search github --db pessoal # busca apenas em 'pessoal'
/keepass show "Grupo/Entrada"       # exibe detalhes (senha visível)
/keepass list --db trabalho         # lista entradas de um banco específico
/keepass add "Dev/nova-api" --db trabalho
/keepass list-dbs                   # mostra todos os bancos configurados
```

### Primeiro uso (sem configuração)

Se `~/.claude/keepass-config.json` não existir:

```
Execute /keepass-setup para configurar seus bancos KeePass.
O wizard vai guiar você pela configuração passo a passo.
```
