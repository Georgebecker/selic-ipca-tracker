# Pasta das imagens do README

Capturas reais do dashboard (`/app/`), feitas em 15/10/2026 com o servidor local.

| Arquivo | O que mostra |
|---|---|
| `dashboard-desktop.png` | Página inteira em 1440 px: KPIs, expectativas do Focus, gráfico comparativo, calculadora e tabela dos últimos 12 meses. |
| `dashboard-mobile.png` | A mesma página em 390 px (celular), com a coluna do mês fixa e a tabela rolando na horizontal. |
| `painel-expectativas.png` | Só o painel "Expectativas do mercado (Focus)": mediana esperada, faixa, respondentes e a diferença em p.p. contra o realizado. |
| `calculadora.png` | Calculadora de correção monetária depois de um cálculo (R$ 1.000 pelo IPCA de 01/01/2020 a 15/10/2026). |

Como regravar (com o servidor no ar):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\servir.ps1
```

Depois abra <http://127.0.0.1:8000/app/> e salve as capturas nesta pasta. Os números
mudam a cada coleta — se a imagem ficar velha, regrave e o README acompanha.
