# Skill: ws_create

Cria um workspace sandboxed em `workspaces/<name>/` com sua própria sub-MIL (context/session.jsonl).

Workspaces são ambientes de execução isolados para projetos. Cada workspace tem seu próprio log de sessão mas compartilha a identidade global.

## Usage

```json
{
  "skill": "ws_create",
  "params": {
    "name":        "projeto-alpha",
    "description": "Implementar o módulo de autenticação OAuth2"
  }
}
```

## Directory structure created

```
workspaces/<name>/
├── context/
│   └── session.jsonl   ← log local do workspace (ACP envelopes)
├── inbox/              ← inbox local (para skills que escrevem no workspace)
└── spool/              ← spool local
```
