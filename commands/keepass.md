---
description: "Gerencia entradas em múltiplos bancos KeePass configurados em ~/.claude/keepass-config.json"
argument-hint: "<operação> [args] [--db <alias>] — ex: search github, show Servers/prod, list --db pessoal"
allowed-tools:
  - Bash
---

# KeePass CLI Command — Multi-Database

Manipula entradas em múltiplos bancos de dados KeePass usando `keepassxc-cli`.

A lista de bancos disponíveis é lida de `~/.claude/keepass-config.json`.
Para configurar pela primeira vez, use `/keepass-setup`.

## Como Usar

Execute operações com: `/keepass <operação> [argumentos] [--db <alias>]`

**Por padrão, opera em TODAS as databases. Use `--db <alias>` para filtrar.**

### Operações disponíveis

| Operação | Descrição |
|----------|-----------|
| `list [--db <alias>]` | Listar todas as entradas |
| `search <termo> [--db <alias>]` | Buscar por nome, username, URL ou notas |
| `show "<grupo/entrada>" [--db <alias>]` | Exibir detalhes (inclui senha em texto claro) |
| `add "<grupo/entrada>" [--db <alias>]` | Adicionar nova entrada com senha gerada |
| `edit "<grupo/entrada>" [--db <alias>]` | Editar entrada existente |
| `rm "<grupo/entrada>" [--db <alias>]` | Mover entrada para Lixeira |
| `totp "<grupo/entrada>" [--db <alias>]` | Gerar código TOTP (2FA) atual da entrada |
| `generate` | Gerar senha aleatória (sem salvar) |
| `db-info [--db <alias>]` | Informações do banco |
| `list-dbs` | Listar todas as databases configuradas |

## Implementação

### Passo 0: Validações obrigatórias

```bash
CONFIG="$HOME/.claude/keepass-config.json"

# ── Abstração Cross-Platform ──────────────────────────────────────────────────

# Detecta o OS atual → "macos" ou "linux"
detect_os() {
  case "$(uname -s)" in
    Darwin) echo "macos" ;;
    Linux)  echo "linux" ;;
    *)      echo "unsupported" ;;
  esac
}

# Recupera senha do secret store do OS
# Uso: get_password "keepassxc-cli" "keepass-pessoal"
get_password() {
  local service="$1" account="$2"
  case "$(detect_os)" in
    macos) security find-generic-password -s "$service" -a "$account" -w 2>/dev/null ;;
    linux) secret-tool lookup service "$service" account "$account" 2>/dev/null ;;
    *)     echo "❌ OS não suportado. Use macOS ou Linux/WSL." >&2; return 1 ;;
  esac
}

# Retorna o caminho do keepassxc-cli
find_keepassxc_cli() {
  if command -v keepassxc-cli &>/dev/null; then
    command -v keepassxc-cli; return
  fi
  case "$(detect_os)" in
    macos)
      for p in /opt/homebrew/bin/keepassxc-cli /usr/local/bin/keepassxc-cli; do
        [ -x "$p" ] && echo "$p" && return
      done ;;
    linux)
      for p in /usr/bin/keepassxc-cli /usr/local/bin/keepassxc-cli; do
        [ -x "$p" ] && echo "$p" && return
      done ;;
  esac
  echo ""
}

# Verifica se KeePassXC desktop está em execução
check_desktop_running() {
  pgrep -x "KeePassXC" > /dev/null 2>&1
}

# Imprime comando para armazenar senha no secret store do OS
store_password_instruction() {
  local service="$1" account="$2"
  case "$(detect_os)" in
    macos) echo "security add-generic-password -s \"$service\" -a \"$account\" -w" ;;
    linux) echo "secret-tool store --label=\"$account\" service \"$service\" account \"$account\"" ;;
  esac
}

# ── Validações ────────────────────────────────────────────────────────────────

# keepassxc-cli instalado?
KEEPASSXC=$(find_keepassxc_cli)
if [ -z "$KEEPASSXC" ]; then
  case "$(detect_os)" in
    macos) echo "❌ keepassxc-cli não encontrado. Instale com: brew install keepassxc" ;;
    linux) echo "❌ keepassxc-cli não encontrado. Instale com: sudo apt install keepassxc" ;;
  esac
  exit 1
fi

# Arquivo de configuração existe?
if [ ! -f "$CONFIG" ]; then
  echo "❌ Configuração não encontrada: $CONFIG"
  echo "   Execute /keepass-setup para configurar seus bancos."
  exit 1
fi

# Para operações de ESCRITA (add/edit/rm): KeePassXC desktop deve estar fechado
check_no_desktop() {
  if check_desktop_running; then
    echo "⚠️  KeePassXC desktop está aberto."
    echo "   Feche o app antes de operações de escrita para evitar conflitos."
    return 1
  fi
}
```

### Passo 1: Resolver aliases

```bash
# Listar todos os aliases disponíveis
get_all_aliases() {
  jq -r '.databases[].alias' "$CONFIG"
}

# Obter info de um banco pelo alias
get_db_info() {
  local alias="$1"
  local info
  info=$(jq ".databases[] | select(.alias == \"$alias\")" "$CONFIG")
  if [ -z "$info" ]; then
    echo "❌ Alias '$alias' não encontrado. Aliases disponíveis:"
    jq -r '.databases[] | "  • \(.alias) — \(.description)"' "$CONFIG"
    return 1
  fi
  echo "$info"
}
```

### Passo 2: Executar operação em um banco

```bash
run_on_db() {
  local db_info="$1"
  local op="$2"      # ls, search, show, add, edit, rm, totp, db-info
  local args="$3"    # argumentos adicionais

  local alias path keychain_service keychain_account keyfile
  alias=$(echo "$db_info" | jq -r '.alias')
  path=$(echo "$db_info" | jq -r '.path')
  keychain_service=$(echo "$db_info" | jq -r '.keychain_service')
  keychain_account=$(echo "$db_info" | jq -r '.keychain_account')
  keyfile=$(echo "$db_info" | jq -r '.keyfile // empty')

  # Arquivo existe?
  if [ ! -f "$path" ]; then
    echo "⚠️  [$alias] Arquivo não encontrado: $path"
    echo "   Verifique se o armazenamento em nuvem está sincronizado."
    return 1
  fi

  # Recuperar senha do Keychain
  local pass
  pass=$(get_password "$keychain_service" "$keychain_account")
  if [ -z "$pass" ]; then
    echo "❌ [$alias] Senha não encontrada no Keychain para '$keychain_account'"
    echo "   Execute: security add-generic-password -s \"$keychain_service\" -a \"$keychain_account\" -w"
    return 1
  fi

  # Executar
  local result exit_code
  if [ -n "$keyfile" ] && [ -f "$keyfile" ]; then
    result=$(printf '%s' "$pass" | "$KEEPASSXC" $op -q -k "$keyfile" "$path" $args 2>&1)
  else
    result=$(printf '%s' "$pass" | "$KEEPASSXC" $op -q "$path" $args 2>&1)
  fi
  exit_code=$?

  # Tratar erros conhecidos
  if [ $exit_code -ne 0 ]; then
    if echo "$result" | grep -qi "already locked\|in use\|locked by"; then
      echo "❌ [$alias] Database bloqueada por outro processo. Feche o KeePassXC desktop."
    elif echo "$result" | grep -qi "invalid credentials\|wrong key\|password"; then
      echo "❌ [$alias] Senha master incorreta no Keychain."
      echo "   Atualize: security delete-generic-password -s \"$keychain_service\" -a \"$keychain_account\""
      echo "   Depois:   security add-generic-password -s \"$keychain_service\" -a \"$keychain_account\" -w"
    elif echo "$result" | grep -qi "entry.*not found\|no entry"; then
      : # saída vazia é normal para "não encontrado" — não mostrar erro
    else
      echo "❌ [$alias] $result"
    fi
    return $exit_code
  fi

  # Prefixar resultado com alias quando buscando em múltiplos bancos
  [ -n "$result" ] && echo "$result" | sed "s/^/[$alias] /"
  return 0
}
```

### Passo 3: Lógica principal

```bash
# Se --db especificado: operar apenas naquele banco
# Se não: iterar sobre todos os bancos e agregar resultados

if [ -n "$DB_FILTER" ]; then
  db_info=$(get_db_info "$DB_FILTER") || exit 1
  run_on_db "$db_info" "$OP" "$ARGS"
else
  for alias in $(get_all_aliases); do
    db_info=$(get_db_info "$alias")
    run_on_db "$db_info" "$OP" "$ARGS"
  done
fi
```

---

## Referência de Operações

### `list`

```bash
printf '%s' "$pass" | "$KEEPASSXC" ls -q -R -f "$path"
```

### `search <termo>`

```bash
printf '%s' "$pass" | "$KEEPASSXC" search -q "$path" "termo"
```

### `show "<entrada>"`

```bash
printf '%s' "$pass" | "$KEEPASSXC" show -q -s --all "$path" "Grupo/Entrada"
```

⚠️ Exibe senha em texto claro. Avisar o usuário antes de executar.

### `add "<entrada>"`

**Verificar KeePassXC desktop fechado antes.**

```bash
# Com senha gerada (recomendado)
printf '%s' "$pass" | "$KEEPASSXC" add -q -g -L 24 -l -U -n -s "$path" "Grupo/Entrada"

# Com username e URL
printf '%s' "$pass" | "$KEEPASSXC" add -q -g -L 24 -l -U -n -s \
  -u "usuario" --url "https://exemplo.com" "$path" "Grupo/Entrada"
```

Flags de geração de senha: `-g` gerar | `-L 24` comprimento | `-l` lowercase | `-U` uppercase | `-n` números | `-s` símbolos

### `edit "<entrada>"`

**Verificar KeePassXC desktop fechado antes.**

```bash
# Editar campos
printf '%s' "$pass" | "$KEEPASSXC" edit -q -u "novo_usuario" --url "https://novo.com" "$path" "Grupo/Entrada"

# Gerar nova senha
printf '%s' "$pass" | "$KEEPASSXC" edit -q -g -L 24 -l -U -n -s "$path" "Grupo/Entrada"
```

### `rm "<entrada>"`

**Verificar KeePassXC fechado. SEMPRE pedir confirmação explícita antes de executar.**

```bash
printf '%s' "$pass" | "$KEEPASSXC" rm -q "$path" "Grupo/Entrada"
```

Move para Lixeira. Para deletar permanentemente, executar `rm` novamente dentro de `Recycle Bin/`.

### `totp "<entrada>"`

```bash
printf '%s' "$pass" | "$KEEPASSXC" show -q --totp "$path" "Grupo/Entrada"
```

Gera o código TOTP atual (6 dígitos, válido por 30s). A entrada precisa ter TOTP configurado no KeePassXC.
Compatível com keepassxc-cli v2.7.x+. O subcomando `totp` só existe na v2.8+.

### `generate`

```bash
"$KEEPASSXC" generate -L 24 -l -U -n -s
```

### `list-dbs`

```bash
jq -r '.databases[] | "[\(.alias)] \(.description) — \(.path)"' "$CONFIG"
```

---

## Regras de Segurança

1. **Nunca expor a senha master** — sempre via stdin pipe; jamais em argumento CLI ou echo visível
2. **Confirmar antes de `rm`** — perguntar: "Confirma exclusão de 'X'? (s/n)"
3. **Verificar KeePassXC fechado** antes de `add`/`edit`/`rm` — `pgrep -x KeePassXC`
4. **Validar `$pass` não-vazio** antes do pipe — erro claro se Keychain falhou
5. **Validar arquivo existe** — `test -f "$path"` antes de qualquer operação
6. **Usar aspas duplas** — caminhos têm espaços; sempre `"$path"`, nunca `$path`
7. **Avisar sobre texto claro** — ao usar `show`, mencionar que senha ficará visível
8. **Aguardar sync** — após writes, informar que armazenamento em nuvem pode levar alguns segundos

## Diagnóstico

```bash
# keepassxc-cli instalado?
find_keepassxc_cli && echo "✓ encontrado" || echo "✗ não encontrado"

# KeePassXC desktop aberto? (deve estar fechado para writes)
check_desktop_running && echo "⚠️ Aberto" || echo "✓ Fechado"

# JSON válido?
jq . ~/.claude/keepass-config.json

# Keychain/secret-tool configurado para um banco?
# macOS:
security find-generic-password -s "keepassxc-cli" -a "KEYCHAIN_ACCOUNT" -w 2>&1 | head -c 3 | xxd
# Linux/WSL:
secret-tool lookup service "keepassxc-cli" account "KEYCHAIN_ACCOUNT"

# Arquivo .kdbx acessível?
test -f "CAMINHO" && echo "✓" || echo "✗ (nuvem sincronizada?)"
```
