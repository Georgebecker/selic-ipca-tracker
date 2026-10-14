# selic-ipca-tracker

[![CI](https://github.com/Georgebecker/selic-ipca-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Georgebecker/selic-ipca-tracker/actions/workflows/ci.yml)

## Classificação

| Dimensão | Valor |
|----------|-------|
| **Propósito** | `estudo` · `utilidade` |
| **Maturidade** | `estável` |
| **O que estou treinando** | séries temporais, composição de taxas, banco SQLite, layout responsivo |
| **Quem usaria** | devs iniciantes, curiosos sobre inflação e juros no Brasil |

> Nota de honestidade (regras R-CL1, R-CL2 e R-CL5 do `modelo.md`), conferida em
> 14/10/2026:
> - `estável` exige README + testes passando + push + **CI** + **release** + manutenção
>   contínua. Está tudo de pé: 57 testes, CI verde em Python 3.12 e 3.13
>   (`actions/workflows/ci.yml`), release **v0.2.0** publicada e o Loop de melhoria
>   contínua rodando com registro em `meu-loop-agente/log.md`.
> - O propósito **não** inclui `entrega` porque ainda não há uso real demonstrado por
>   terceiros (R-CL1: `entrega` exige README, teste e uso real). Hoje o repositório é
>   privado e sem usuários externos — dizer `entrega` seria inflar a classificação.

Acompanhamento de indicadores econômicos brasileiros (Selic, IPCA, IGP-M e INPC)
com coleta no Banco Central, banco SQLite, API REST documentada e dashboard web
responsivo (dark mode, gráficos comparativos, calculadora de correção monetária e
atualização sob demanda por botão — os dados são mensais, não há contagem regressiva).

## Como rodar

```powershell
# 1. dependências
python -m pip install -r requirements.txt

# 2. configuração local (opcional: o padrão já funciona)
Copy-Item .env.example .env

# 3. primeira coleta de dados (BCB/SGS)
python -m src.etl.coleta

# 4. subir a API + dashboard
uvicorn src.api.main:app --reload
```

- Documentação interativa (Swagger): <http://localhost:8000/docs>
- Dashboard: <http://localhost:8000/app/>

Com Docker: `docker compose up --build`.

Repositório: `https://github.com/Georgebecker/selic-ipca-tracker` (privado), branch
`master`. Chave de API não vai em arquivo: vive na variável de ambiente do usuário
(ver `REGRAS_DE_OURO.md`, R36).

## Fonte de dados

Tudo vem de APIs públicas do Banco Central, sem chave:

- **SGS (séries temporais)**: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados`
- **Olinda (Focus/expectativas)**: `https://olinda.bcb.gov.br` (opcional, ainda não usado)

| Série | Código SGS | Periodicidade |
|---|---|---|
| Selic meta | 432 | diária |
| Selic acumulada no mês | 4390 | mensal |
| IPCA mensal | 433 | mensal |
| IPCA acumulado 12 meses | 13522 | mensal |
| IGP-M mensal | 189 | mensal |
| INPC mensal | 188 | mensal |
| CDI diário | 12 | diária |
| Dólar PTAX venda | 1 | diária |
| IPCA-15 | 7478 | mensal |
| INCC-DI | 192 | mensal |
| IGP-DI | 190 | mensal |
| Poupança | 25 | mensal |

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/series` | Lista as séries disponíveis |
| GET | `/series/{codigo}/dados` | Série completa (filtros `?de=` e `?ate=`) |
| GET | `/series/{codigo}/ultimos/{n}` | Últimos N valores |
| GET | `/indicadores/resumo` | KPIs: Selic, IPCA, IGP-M e INPC (atual + 12 meses) |
| GET | `/comparacao` | Compara índices mês a mês (`?series=433,189`) |
| POST | `/calculadora/corrigir` | Corrige um valor pela inflação do período |
| POST | `/atualizar` | Inicia a coleta em segundo plano (HTTP 202) |
| GET | `/status` | Estado do serviço + progresso da coleta |

## Estrutura

```
selic-ipca-tracker/
├── src/
│   ├── config.py             # leitura do .env e caminhos do projeto
│   ├── etl/                  # bcb_sgs.py, limpeza.py, coleta.py
│   ├── db/                   # models.py (SQLAlchemy), repository.py
│   ├── analise/              # calculos.py, comparacao.py
│   ├── api/                  # main.py, schemas.py, routers/
│   └── scheduler/timer.py    # agendador opcional (APScheduler)
├── frontend/                 # index.html, style.css, app.js (Chart.js)
├── tests/                    # test_etl, test_calculos, test_api, test_classificacao
├── sql/schema.sql            # esquema do banco (referência)
├── meu-loop-agente/          # contrato e verificador do Loop de melhoria contínua
└── data/                     # banco SQLite local (fora do git)
```

## Loop de melhoria contínua

O agente que melhora este projeto em ciclos fica em `meu-loop-agente/`
(metodologia Loop Engineering). Contrato, métrica e limites em
`meu-loop-agente/program.md` e `meu-loop-agente/config_loop.json`; histórico das
iterações em `meu-loop-agente/log.md` e decisões de projeto em `log_loop.md`.

```powershell
python meu-loop-agente/verificar_iteracao.py estado      # situação atual do Loop
python meu-loop-agente/medir_qualidade.py --detalhe      # métrica score_qualidade
python -m pytest -q                                      # verificação obrigatória
```

## Operação

Três scripts em `scripts/` para o dia a dia (nenhum deles guarda segredo):

```powershell
# subir a API + dashboard (Ctrl+C encerra)
powershell -ExecutionPolicy Bypass -File scripts\servir.ps1
powershell -ExecutionPolicy Bypass -File scripts\servir.ps1 -Porta 8080 -Recarregar -AbrirNavegador

# atualizar os dados (paralelo, com retentativa automática das séries que falharem)
powershell -ExecutionPolicy Bypass -File scripts\coletar.ps1
powershell -ExecutionPolicy Bypass -File scripts\coletar.ps1 -Series 433,189 -Workers 10

# backup do banco (data no nome, verificação de que o arquivo abre e retenção dos 10 últimos)
powershell -ExecutionPolicy Bypass -File scripts\backup.ps1
powershell -ExecutionPolicy Bypass -File scripts\backup.ps1 -Listar
```

O serviço vive enquanto a janela do `servir.ps1` estiver aberta. O `backup.ps1` grava em
`data/backups/` (fora do git) e apaga os mais antigos conforme `-Manter`.

## Qualidade

- **74 testes** (`python -m pytest -q`) — ETL, coleta (paralelismo, retentativa, falhas),
  execução em segundo plano, cálculos, API, classificação, responsividade do front-end e
  consistência entre `sql/schema.sql` e o modelo SQLAlchemy.
- **CI** (`.github/workflows/ci.yml`): a cada push/PR roda os testes em Python 3.12 e 3.13,
  compila os módulos, confere que nenhum arquivo de segredo está versionado e sobe a
  aplicação para checar `/status`, `/series` e `/docs`.
- **Guarda local**: o mesmo teste de segredo roda no `pre-commit`/`pre-push` (ver
  `REGRAS_DE_OURO.md`, R36) — a proteção não depende do CI.
- **Loop de melhoria contínua**: métrica `score_qualidade` com histórico em
  `meu-loop-agente/log.md`.

## Limitações

- A API do SGS recusa janelas maiores que 10 anos em séries diárias e exige
  `dataInicial` e `dataFinal` juntos; o cliente divide o período em janelas de 9 anos.
- O SGS publica a Selic meta com datas à frente (até a próxima reunião do Copom).
- A atualização é **manual**: os indicadores são mensais, então o dashboard tem apenas
  o botão "Atualizar" (sem contagem regressiva). `GET /status` informa a última coleta.
- Existe **coleta automática opcional**, desligada por padrão: com
  `COLETA_AUTOMATICA=true` (e opcionalmente `COLETA_INTERVALO_HORAS`, padrão 24) o
  servidor agenda a coleta sozinho via APScheduler (`src/scheduler/timer.py`).
  `GET /status` informa se está ligada (`coleta_automatica`).
- O CDN do Chart.js exige internet para desenhar o gráfico.
- A coleta roda **em segundo plano**: `POST /atualizar` responde na hora (HTTP 202) e o
  progresso aparece em `GET /status` (`coleta.concluidas` / `coleta.total_series`), que o
  botão do dashboard mostra como "Coletando 3/12…". Uma coleta por vez: a segunda chamada
  apenas lê o progresso.
- As séries são baixadas em paralelo (6 threads por padrão, `--workers` para ajustar):
  medido nesta máquina, a execução quente caiu de ~9 s (sequencial) para ~5 s, e a
  primeira carga do histórico completo, de 201 s para 73 s.

## Licença

MIT — ver [LICENSE](./LICENSE).
