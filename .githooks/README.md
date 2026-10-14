# Ganchos de protecao do git

## O que protege

- `pre-commit` — bloqueia qualquer commit que tente incluir `.env` ou variantes
  (`.env.local`, `.env.prod` etc.). O unico arquivo `.env*` permitido e o
  `.env.example` (modelo sem segredos).

- `pre-push` — segunda barreira: antes de enviar ao repositorio remoto, confere
  todos os commits que serao enviados e bloqueia o push se algum contiver
  `.env` ou variantes. Protege mesmo se um commit passou com `--no-verify`.

Juntas, elas formam a regra "o `.env` NUNCA vai para o git": funcionam mesmo
se alguem usar `git add -f` ou `git add .` sem conferir, ou tentar burlar o commit.

## Como ativar (uma vez so)

Repositorio ainda nao criado:

```powershell
powershell -ExecutionPolicy Bypass -File .githooks\instalar.ps1
```

Repositorio ja criado, so ativar os ganchos:

```powershell
git config core.hooksPath .githooks
```

## Como conferir se esta ativo

```powershell
git config core.hooksPath
```

Tem que responder `.githooks`. Tambem vale conferir que os arquivos
`.githooks\pre-commit` e `.githooks\pre-push` existem.

## Teste rapido (opcional)

Crie um arquivo `.env` de mentira, tente `git add .env` + `git commit`:
o commit tem que ser recusado com a mensagem "BLOQUEADO".

Para testar o `pre-push` sem risco: crie um repositorio de teste em pasta
temporaria, adicione um `.env`, faca o commit com `--no-verify` e tente
`git push` para um remoto de mentira — o push tem que ser bloqueado.
