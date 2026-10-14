# selic-ipca-tracker

## Classificação

| Dimensão | Valor |
|----------|-------|
| **Propósito** | `estudo` · `utilidade` |
| **Maturidade** | `usável` |
| **O que estou treinando** | séries temporais, composição de taxas, banco SQLite, layout responsivo |
| **Quem usaria** | devs iniciantes, curiosos sobre inflação e juros no Brasil |

> Nota de honestidade (regras R-CL1, R-CL2 e R-CL5 do `modelo.md`): a maturidade é
> `usável` porque o projeto tem README, testes passando e está publicado no GitHub
> (repositório privado, `origin` em `master`). O propósito **não** inclui `entrega`
> porque ainda não há uso real demonstrado por terceiros. Para chegar a `estável`
> faltam CI configurado, releases tagueadas e manutenção contínua. Esta tabela é
> reavaliada a cada ciclo do Loop de melhoria contínua (§1.1.5 do `modelo.md`).

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
| POST | `/atualizar` | Força a coleta agora |
| GET | `/status` | Última coleta e séries monitoradas |

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

## Limitações

- A API do SGS recusa janelas maiores que 10 anos em séries diárias e exige
  `dataInicial` e `dataFinal` juntos; o cliente divide o período em janelas de 9 anos.
- O SGS publica a Selic meta com datas à frente (até a próxima reunião do Copom).
- A atualização é **manual**: os indicadores são mensais, então o dashboard tem apenas
  o botão "Atualizar" (sem contagem regressiva). `GET /status` informa a última coleta.
  O agendador do back-end (`src/scheduler/timer.py`, APScheduler) é opcional e não é
  usado pela interface.
- O CDN do Chart.js exige internet para desenhar o gráfico.
- `/atualizar` é síncrono: com 12 séries a coleta leva alguns segundos.

## Licença

MIT — ver [LICENSE](./LICENSE).
