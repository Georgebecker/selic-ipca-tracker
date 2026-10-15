-- Esquema do banco do selic-ipca-tracker (referencia do modelo SQLAlchemy).
-- Referencia: o SQLAlchemy cria exatamente estas tabelas na subida da aplicacao
-- (src/db/models.py). Este arquivo serve para consulta manual e para recriar o
-- banco sem Python.

CREATE TABLE IF NOT EXISTS series (
    id            INTEGER PRIMARY KEY,
    codigo_sgs    INTEGER UNIQUE NOT NULL,
    nome          TEXT NOT NULL,
    descricao     TEXT,
    unidade       TEXT,
    periodicidade TEXT,
    fonte         TEXT DEFAULT 'BCB/SGS'
);

CREATE TABLE IF NOT EXISTS valores (
    id          INTEGER PRIMARY KEY,
    serie_id    INTEGER NOT NULL REFERENCES series(id),
    data        DATE NOT NULL,
    valor       REAL NOT NULL,
    coletado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (serie_id, data)
);

CREATE TABLE IF NOT EXISTS atualizacoes (
    id                 INTEGER PRIMARY KEY,
    data_hora          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tipo               TEXT NOT NULL,   -- 'automatica' | 'manual'
    series_atualizadas INTEGER DEFAULT 0,
    status             TEXT NOT NULL,   -- 'sucesso' | 'parcial' | 'erro'
    mensagem           TEXT
);

CREATE INDEX IF NOT EXISTS idx_valores_serie_data ON valores (serie_id, data);
CREATE INDEX IF NOT EXISTS idx_series_codigo ON series (codigo_sgs);

-- Seed das series acompanhadas.
INSERT OR IGNORE INTO series (codigo_sgs, nome, unidade, periodicidade) VALUES
    (432,   'Selic meta',               '% a.a.', 'diaria'),
    (4390,  'Selic acumulada no mes',   '%',      'mensal'),
    (433,   'IPCA mensal',              '%',      'mensal'),
    (13522, 'IPCA acumulado 12 meses',  '%',      'mensal'),
    (189,   'IGP-M mensal',             '%',      'mensal'),
    (188,   'INPC mensal',              '%',      'mensal'),
    (12,    'CDI diario',               '% a.d.', 'diaria'),
    (1,     'Dolar PTAX venda',         'R$',     'diaria'),
    (7478,  'IPCA-15',                  '%',      'mensal'),
    (192,   'INCC-DI',                  '%',      'mensal'),
    (190,   'IGP-DI',                   '%',      'mensal'),
    (25,    'Poupanca',                 '%',      'mensal');
