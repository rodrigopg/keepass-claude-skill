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

---

## PROIBIÇÕES ABSOLUTAS — Jamais faça isso

❌ **NUNCA usar `export`** — exporta TODAS as senhas em texto puro. Proibido sem exceção.
❌ **NUNCA hardcodar senha** — nem "master", nem qualquer outra. Se Keychain falhar, parar e reportar.
❌ **NUNCA usar `find` para localizar arquivos `.kdbx`** — se o arquivo não existir no caminho do config, reportar e parar.
❌ **NUNCA sobrescrever senha no Keychain automaticamente** — nunca executar `security add/delete-generic-password` sem pedido explícito do usuário.
❌ **NUNCA tentar mais de 1 vez a mesma operação** — se falhar, reportar o erro exato e parar.
❌ **NUNCA adivinhar caminho de entrada** — sempre fazer `search` primeiro para obter o caminho exato.
❌ **NUNCA usar `echo "$pass"` com pipe** — usar sempre `printf '%s\n' "$pass"` para consistência.

---

## Como Usar

Execute operações com: `/keepass <operação> [argumentos] [--db <alias>]`

**Por padrão, opera em TODAS as databases. Use `--db <alias>` para filtrar.**

### Operações disponíveis

| Operação | Descrição |
|----------|-----------|
| `list [--db <alias>]` | Listar todas as entradas |
| `search <termo> [--db <alias>]` | Buscar por nome, username, URL ou notas |
| `show "<grupo/entrada>" [--db <alias>]` | Exibir detalhes — SEMPRE fazer `search` antes |
| `add "<grupo/entrada>" [--db <alias>]` | Adicionar nova entrada com senha gerada |
| `edit "<grupo/entrada>" [--db <alias>]` | Editar entrada existente |
| `rm "<grupo/entrada>" [--db <alias>]` | Mover entrada para Lixeira — pede confirmação |
| `totp "<grupo/entrada>" [--db <alias>]` | Gerar código TOTP (2FA) atual da entrada |
| `generate` | Gerar senha aleatória (sem salvar) |
| `db-info [--db <alias>]` | Informações do banco |
| `list-dbs` | Listar todas as databases configuradas |

### Fluxo obrigatório para `show`

```
1. Executar: search <termo>
2. Apresentar os resultados ao usuário
3. Usar o caminho EXATO retornado pelo search para executar o show
4. Nunca construir ou adivinhar o caminho — usar apenas o que o search retornou
```

---

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
      for p in /opt/homebrew/bin/keepassxc-cli /usr/local/bin/keepassxc-cli \
                /Applications/KeePassXC.app/Contents/MacOS/keepassxc-cli; do
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

# ── Validações ────────────────────────────────────────────────────────────────

# jq instalado?
if ! command -v jq &>/dev/null; then
  case "$(detect_os)" in
    macos) echo "❌ jq não encontrado. Instale com: brew install jq" ;;
    linux) echo "❌ jq não encontrado. Instale com: sudo apt install jq" ;;
  esac
  exit 1
fi

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
```

### Passo 1: Resolver aliases

```bash
# Listar todos os aliases disponíveis
get_all_aliases() {
  jq -r '.databases[].alias' "$CONFIG"
}

# Obter info de um banco pelo alias (usa --arg para evitar injeção por alias com aspas)
get_db_info() {
  local alias="$1"
  local info
  info=$(jq --arg alias "$alias" '.databases[] | select(.alias == $alias)' "$CONFIG")
  if [ -z "$info" ]; then
    echo "❌ Alias '$alias' não encontrado. Aliases disponíveis:"
    jq -r '.databases[] | "  • \(.alias)"' "$CONFIG"
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
  local args="$3"    # argumentos adicionais (string, expandida pelo chamador)

  local alias path keychain_service keychain_account keyfile
  alias=$(echo "$db_info" | jq -r '.alias')
  path=$(echo "$db_info" | jq -r '.path')
  keychain_service=$(echo "$db_info" | jq -r '.keychain_service')
  keychain_account=$(echo "$db_info" | jq -r '.keychain_account')
  keyfile=$(echo "$db_info" | jq -r '.keyfile // empty')

  # Para operações de ESCRITA: KeePassXC desktop deve estar fechado
  if [[ "$op" =~ ^(add|edit|rm)$ ]]; then
    if check_desktop_running; then
      echo "❌ [$alias] KeePassXC desktop está aberto."
      echo "   Feche o app antes de operações de escrita para evitar conflitos de lock."
      return 1
    fi
  fi

  # Arquivo existe? Parar imediatamente — não buscar alternativas.
  if [ ! -f "$path" ]; then
    echo "❌ [$alias] Arquivo não encontrado: $path"
    echo "   Verifique se o armazenamento em nuvem está sincronizado."
    echo "   Se o caminho mudou, atualize ~/.claude/keepass-config.json manualmente."
    return 1
  fi

  # Recuperar senha do Keychain — se falhar, parar imediatamente
  local pass
  pass=$(get_password "$keychain_service" "$keychain_account")
  if [ -z "$pass" ]; then
    echo "❌ [$alias] Senha não encontrada no Keychain para '$keychain_account'"
    echo "   Para corrigir, execute manualmente no terminal:"
    echo "   security add-generic-password -s \"$keychain_service\" -a \"$keychain_account\" -w"
    echo "   (nunca executar automaticamente — requer a senha master digitada pelo usuário)"
    return 1
  fi

  # Executar — usar printf '%s\n' para evitar interpretação de flags
  local result exit_code
  if [ -n "$keyfile" ] && [ -f "$keyfile" ]; then
    result=$(printf '%s\n' "$pass" | "$KEEPASSXC" "$op" -q -k "$keyfile" "$path" $args 2>&1)
  else
    result=$(printf '%s\n' "$pass" | "$KEEPASSXC" "$op" -q "$path" $args 2>&1)
  fi
  exit_code=$?

  # Tratar erros conhecidos — reportar e parar, sem retentativas
  if [ $exit_code -ne 0 ]; then
    if echo "$result" | grep -qi "already locked\|in use\|locked by"; then
      echo "❌ [$alias] Database bloqueada por outro processo. Feche o KeePassXC desktop."
    elif echo "$result" | grep -qi "invalid credentials\|wrong key\|Invalid key\|error.*password\|Error while reading"; then
      echo "❌ [$alias] Senha master incorreta no Keychain para '$keychain_account'."
      echo "   Para corrigir manualmente (execute você mesmo no terminal):"
      echo "   1. security delete-generic-password -s \"$keychain_service\" -a \"$keychain_account\""
      echo "   2. security add-generic-password -s \"$keychain_service\" -a \"$keychain_account\" -w"
    elif echo "$result" | grep -qi "entry.*not found\|no entry\|Could not find"; then
      echo "⚠️  [$alias] Entrada não encontrada."
      echo "   Use 'search <termo>' para localizar o caminho exato da entrada."
    else
      echo "❌ [$alias] Erro (exit $exit_code): $result"
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
printf '%s\n' "$pass" | "$KEEPASSXC" ls -q -R -f "$path"
```

### `search <termo>`

```bash
printf '%s\n' "$pass" | "$KEEPASSXC" search -q "$path" "termo"
```

Retorna caminhos exatos das entradas. **Use esses caminhos para `show`.**

### `show "<entrada>"` — SEMPRE fazer `search` antes

```bash
# PASSO 1: buscar para obter o caminho exato
printf '%s\n' "$pass" | "$KEEPASSXC" search -q "$path" "termo"

# PASSO 2: usar o caminho EXATO retornado pelo search (copiar sem modificar)
printf '%s\n' "$pass" | "$KEEPASSXC" show -q -s --all "$path" "Grupo/Entrada/Exata"
```

⚠️ Exibe senha em texto claro. Avisar o usuário antes de executar.
⚠️ Se o usuário não forneceu o caminho exato, executar search e perguntar qual entrada mostrar.

### `add "<entrada>"`

KeePassXC desktop deve estar fechado (verificado automaticamente em `run_on_db`).

```bash
# Com senha gerada (recomendado)
printf '%s\n' "$pass" | "$KEEPASSXC" add -q -g -L 24 -l -U -n -s "$path" "Grupo/Entrada"

# Com username e URL
printf '%s\n' "$pass" | "$KEEPASSXC" add -q -g -L 24 -l -U -n -s \
  -u "usuario" --url "https://exemplo.com" "$path" "Grupo/Entrada"
```

Flags: `-g` gerar senha | `-L 24` comprimento | `-l` lowercase | `-U` uppercase | `-n` números | `-s` símbolos

### `edit "<entrada>"`

KeePassXC desktop deve estar fechado (verificado automaticamente em `run_on_db`).

```bash
printf '%s\n' "$pass" | "$KEEPASSXC" edit -q -u "novo_usuario" --url "https://novo.com" "$path" "Grupo/Entrada"

# Gerar nova senha
printf '%s\n' "$pass" | "$KEEPASSXC" edit -q -g -L 24 -l -U -n -s "$path" "Grupo/Entrada"
```

### `rm "<entrada>"` — SEMPRE pedir confirmação

**Antes de executar, perguntar ao usuário:**
```
Confirma exclusão de '<entrada>' no banco '<alias>'? (s/n)
```
Só prosseguir se a resposta for "s" ou "sim". Se não, abortar.

```bash
printf '%s\n' "$pass" | "$KEEPASSXC" rm -q "$path" "Grupo/Entrada"
```

Move para Lixeira. Para deletar permanentemente, executar `rm` novamente dentro de `Recycle Bin/`.

### `totp "<entrada>"`

```bash
printf '%s\n' "$pass" | "$KEEPASSXC" show -q --totp "$path" "Grupo/Entrada"
```

Gera o código TOTP atual (6 dígitos, válido por ~30s). A entrada precisa ter TOTP configurado.
Compatível com keepassxc-cli v2.7.x+. O subcomando `totp` só existe na v2.8+.

### `generate`

```bash
"$KEEPASSXC" generate -L 24 -l -U -n -s
```

### `list-dbs`

```bash
jq -r '.databases[] | "[\(.alias)] — \(.path)"' "$CONFIG"
```

### `db-info`

```bash
printf '%s\n' "$pass" | "$KEEPASSXC" db-info -q "$path"
```

---

## Regras de Segurança

1. **Nunca expor a senha master** — sempre via `printf '%s\n' "$pass" | ...`; jamais em argumento CLI
2. **Nunca usar `export`** — expõe TODAS as senhas em texto puro; proibição absoluta
3. **Confirmar antes de `rm`** — perguntar ao usuário; só executar com confirmação explícita
4. **Verificar KeePassXC fechado** antes de `add`/`edit`/`rm` (integrado em `run_on_db`)
5. **Parar na primeira falha** — não tentar variações; reportar o erro exato
6. **Nunca corrigir Keychain automaticamente** — apenas instruir o usuário com os comandos
7. **Usar aspas duplas** — caminhos têm espaços; sempre `"$path"`, nunca `$path`
8. **Avisar sobre texto claro** — ao usar `show`, mencionar que senha ficará visível
9. **Search antes de show** — nunca construir caminhos; usar apenas o que o search retornar

## Diagnóstico

```bash
# jq instalado?
command -v jq && echo "✓" || echo "✗ brew install jq"

# keepassxc-cli instalado?
keepassxc=$(find_keepassxc_cli); [ -n "$keepassxc" ] && echo "✓ $keepassxc" || echo "✗ não encontrado"

# KeePassXC desktop aberto? (deve estar fechado para writes)
pgrep -x KeePassXC && echo "⚠️ Aberto" || echo "✓ Fechado"

# JSON válido?
jq . ~/.claude/keepass-config.json

# Keychain configurado para um banco? (macOS)
security find-generic-password -s "keepassxc-cli" -a "KEYCHAIN_ACCOUNT" -w 2>&1 | head -c 3 | xxd

# Arquivo .kdbx acessível?
test -f "CAMINHO" && echo "✓" || echo "✗ (nuvem sincronizada?)"
```
