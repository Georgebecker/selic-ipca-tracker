/* selic-ipca-tracker — dashboard (Vanilla JS + Chart.js)
   Os dados do BCB sao mensais: nao ha contagem regressiva. A atualizacao e manual,
   pelo botao "Atualizar" (POST /atualizar); GET /status alimenta apenas o texto de
   "ultima coleta" no topo e no rodape. */

const API = '';

const INDICADORES_KPI = ['selic', 'ipca', 'igpm', 'inpc'];

const SERIES_COMPARATIVO = [
  { codigo: 433, rotulo: 'IPCA', chave: 'ipca', cor: '#3ddc97' },
  { codigo: 189, rotulo: 'IGP-M', chave: 'igpm', cor: '#f5a524' },
  { codigo: 188, rotulo: 'INPC', chave: 'inpc', cor: '#c084fc' },
  { codigo: 4390, rotulo: 'Selic (mes)', chave: 'selic', cor: '#4f8cff' }
];

let grafico = null;
let anosSelecionados = 5;

/* ------------------------------- utilidades ------------------------------- */

function formatarPercentual(valor, casas = 2) {
  if (valor === null || valor === undefined) return '—';
  return `${valor.toFixed(casas)}%`;
}

function formatarMoeda(valor) {
  if (valor === null || valor === undefined) return '—';
  return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarData(iso) {
  if (!iso) return '—';
  const [ano, mes, dia] = iso.slice(0, 10).split('-');
  return `${dia}/${mes}/${ano}`;
}

function formatarMes(iso) {
  const [ano, mes] = iso.slice(0, 7).split('-');
  const nomes = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  return `${nomes[Number(mes) - 1]}/${ano.slice(2)}`;
}

function classeSinal(valor) {
  if (valor === null || valor === undefined) return '';
  return valor < 0 ? 'negativo' : 'positivo';
}

async function buscarApi(caminho, opcoes) {
  const resposta = await fetch(API + caminho, opcoes);
  if (!resposta.ok) {
    let detalhe = `${resposta.status} ${resposta.statusText}`;
    try {
      const corpo = await resposta.json();
      if (corpo && corpo.detail) detalhe = corpo.detail;
    } catch (erro) {
      /* resposta sem JSON: mantem o texto do status */
    }
    throw new Error(detalhe);
  }
  return resposta.json();
}

function mostrarAviso(id, mensagem) {
  const elemento = document.getElementById(id);
  if (!elemento) return;
  elemento.textContent = mensagem || '';
  elemento.hidden = !mensagem;
}

/* --------------------------- estado da coleta ----------------------------- */

const INTERVALO_ACOMPANHAR_MS = 1500;
const LIMITE_ACOMPANHAR_MS = 5 * 60 * 1000;

let acompanhando = false;

function atualizarTextoColeta(estado) {
  const coleta = estado.coleta || {};
  const ultima = document.getElementById('ultima-coleta');
  const rodape = document.getElementById('rodape-status');

  if (ultima) {
    if (coleta.em_andamento) {
      ultima.textContent = `coletando ${coleta.concluidas}/${coleta.total_series || '?'}…`;
    } else if (estado.ultima_atualizacao) {
      ultima.textContent = `última coleta: ${formatarData(estado.ultima_atualizacao)}`;
    } else {
      ultima.textContent = 'sem coleta registrada';
    }
  }

  if (rodape) {
    const base = estado.ultima_atualizacao
      ? `Fonte: BCB/SGS. Última coleta: ${formatarData(estado.ultima_atualizacao)}. `
        + `${estado.series_monitoradas} séries monitoradas (dados mensais).`
      : 'Fonte: BCB/SGS. Nenhuma coleta registrada — use o botão "Atualizar".';
    const sufixo = coleta.em_andamento ? ' Coleta em andamento.' : '';
    rodape.textContent = base + sufixo;
  }
}

async function carregarStatus() {
  try {
    const estado = await buscarApi('/status');
    atualizarTextoColeta(estado);
    return estado;
  } catch (erro) {
    const ultima = document.getElementById('ultima-coleta');
    if (ultima) ultima.textContent = `status indisponível (${erro.message})`;
    return null;
  }
}

async function acompanharColeta() {
  if (acompanhando) return true;
  acompanhando = true;

  const botao = document.getElementById('botao-atualizar');
  const limite = Date.now() + LIMITE_ACOMPANHAR_MS;

  try {
    while (Date.now() < limite) {
      const estado = await buscarApi('/status');
      const coleta = estado.coleta || {};
      atualizarTextoColeta(estado);

      if (!coleta.em_andamento) {
        if (coleta.status && coleta.status !== 'sucesso') {
          mostrarAviso('aviso-grafico',
            `Coleta ${coleta.status}${coleta.mensagem ? ': ' + coleta.mensagem : ''}`);
        } else {
          mostrarAviso('aviso-grafico', '');
        }
        return true;
      }

      if (botao) botao.textContent = `Coletando ${coleta.concluidas}/${coleta.total_series || '?'}…`;
      await new Promise((resolver) => setTimeout(resolver, INTERVALO_ACOMPANHAR_MS));
    }
    return false;
  } catch (erro) {
    mostrarAviso('aviso-grafico', `Perdi o contato durante a coleta: ${erro.message}`);
    return false;
  } finally {
    acompanhando = false;
  }
}

async function dispararAtualizacao() {
  const botao = document.getElementById('botao-atualizar');
  if (botao) {
    botao.disabled = true;
    botao.textContent = 'Iniciando…';
  }

  try {
    await buscarApi('/atualizar', { method: 'POST' });
    const terminou = await acompanharColeta();
    if (!terminou && botao) {
      mostrarAviso('aviso-grafico',
        'A coleta segue rodando no servidor; o resultado aparece no topo da página.');
    }
    await Promise.all([carregarResumo(), carregarComparativo(), carregarStatus()]);
  } catch (erro) {
    mostrarAviso('aviso-grafico', `Falha ao atualizar: ${erro.message}`);
  } finally {
    if (botao) {
      botao.disabled = false;
      botao.textContent = 'Atualizar';
    }
  }
}

/* ----------------------------------- KPIs --------------------------------- */

async function carregarResumo() {
  const resumo = await buscarApi('/indicadores/resumo');

  INDICADORES_KPI.forEach((chave) => {
    const dados = resumo[chave];
    const valor = document.getElementById(`kpi-${chave}-valor`);
    const nota = document.getElementById(`kpi-${chave}-nota`);
    const data = document.getElementById(`kpi-${chave}-data`);
    if (!dados) return;

    if (valor) valor.textContent = formatarPercentual(dados.atual);
    if (nota) {
      const acumulado = formatarPercentual(dados.acumulado_12m);
      const oficial = dados.acumulado_12m_oficial !== null
        && dados.acumulado_12m_oficial !== undefined
        ? ` (oficial: ${formatarPercentual(dados.acumulado_12m_oficial)})`
        : '';
      nota.textContent = `acumulado 12 meses: ${acumulado}${oficial}`;
    }
    if (data) data.textContent = dados.data ? `referência: ${formatarData(dados.data)}` : 'sem dados';
  });
}

/* --------------------------- grafico e tabela ----------------------------- */

function inicioDoPeriodo(anos) {
  if (!anos) return null;
  const agora = new Date();
  agora.setFullYear(agora.getFullYear() - anos);
  return agora.toISOString().slice(0, 10);
}

function montarGrafico(eixo, series) {
  const contexto = document.getElementById('grafico-indices');
  if (!contexto || typeof Chart === 'undefined') return;

  // Leitor de tela: descreve o gráfico em texto (o canvas sozinho não diz nada).
  if (eixo.length && series.length) {
    const nomes = series.map((item) => item.nome).join(', ');
    contexto.setAttribute('aria-label',
      `Gráfico comparativo de ${nomes}, de ${formatarMes(eixo[0])} a `
      + `${formatarMes(eixo[eixo.length - 1])} (${eixo.length} meses). `
      + 'Os valores numéricos estão na tabela de últimos 12 meses.');
  }

  const conjuntos = SERIES_COMPARATIVO.map((definicao) => {
    const serie = series.find((item) => item.codigo_sgs === definicao.codigo);
    return {
      label: definicao.rotulo,
      data: serie ? serie.valores : [],
      borderColor: definicao.cor,
      backgroundColor: `${definicao.cor}22`,
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.25,
      spanGaps: true
    };
  });

  const rotulos = eixo.map(formatarMes);

  if (grafico) {
    grafico.data.labels = rotulos;
    grafico.data.datasets = conjuntos;
    grafico.update();
    return;
  }

  grafico = new Chart(contexto, {
    type: 'line',
    data: { labels: rotulos, datasets: conjuntos },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: 'rgba(240,240,240,0.85)' } },
        tooltip: {
          backgroundColor: 'rgba(20,20,24,0.85)',
          borderColor: 'rgba(255,255,255,0.12)',
          borderWidth: 1,
          titleColor: '#fff',
          bodyColor: 'rgba(240,240,240,0.9)',
          callbacks: {
            label: (item) => `${item.dataset.label}: ${formatarPercentual(item.parsed.y)}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.1)' },
          ticks: { color: 'rgba(200,200,200,0.75)', maxRotation: 0, autoSkip: true }
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.1)' },
          ticks: {
            color: 'rgba(200,200,200,0.75)',
            callback: (valor) => `${valor}%`
          }
        }
      }
    }
  });
}

function montarTabela(eixo, series) {
  const corpo = document.getElementById('tabela-recente-corpo');
  if (!corpo) return;

  const ultimos = eixo.map((mes, indice) => ({ mes, indice })).slice(-12).reverse();
  if (!ultimos.length) {
    corpo.innerHTML = '<tr><td colspan="5">sem dados coletados</td></tr>';
    return;
  }

  const porCodigo = new Map(series.map((item) => [item.codigo_sgs, item]));
  corpo.innerHTML = ultimos
    .map(({ mes, indice }) => {
      const celulas = SERIES_COMPARATIVO.map((definicao) => {
        const serie = porCodigo.get(definicao.codigo);
        const valor = serie ? serie.valores[indice] : null;
        return `<td class="${classeSinal(valor)}">${formatarPercentual(valor)}</td>`;
      }).join('');
      return `<tr><td>${formatarMes(mes)}</td>${celulas}</tr>`;
    })
    .join('');
}

async function carregarComparativo() {
  try {
    const parametros = new URLSearchParams();
    const de = inicioDoPeriodo(anosSelecionados);
    if (de) parametros.set('de', de);
    parametros.set('series', SERIES_COMPARATIVO.map((item) => item.codigo).join(','));

    const dados = await buscarApi(`/comparacao?${parametros.toString()}`);
    mostrarAviso('aviso-grafico', '');
    montarGrafico(dados.eixo, dados.series);
    montarTabela(dados.eixo, dados.series);
  } catch (erro) {
    mostrarAviso('aviso-grafico', `Não foi possível carregar o comparativo: ${erro.message}`);
  }
}

/* ------------------------------- calculadora ------------------------------ */

async function corrigirValor(evento) {
  evento.preventDefault();
  const corpo = {
    valor: Number(document.getElementById('calc-valor').value),
    data_inicial: document.getElementById('calc-inicial').value,
    data_final: document.getElementById('calc-final').value,
    indice: document.getElementById('calc-indice').value
  };

  try {
    const resultado = await buscarApi('/calculadora/corrigir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(corpo)
    });

    mostrarAviso('aviso-calculadora', '');
    const caixa = document.getElementById('resultado-calculadora');
    if (caixa) caixa.hidden = false;

    const valor = document.getElementById('resultado-valor');
    if (valor) valor.textContent = formatarMoeda(resultado.valor_corrigido);

    const detalhe = document.getElementById('resultado-detalhe');
    if (detalhe) {
      detalhe.textContent = `${formatarMoeda(resultado.valor_original)} em ${resultado.periodo} `
        + `→ ${formatarMoeda(resultado.valor_corrigido)} (${resultado.indice}, `
        + `${resultado.meses} meses, variação de ${formatarPercentual(resultado.variacao_percentual, 4)})`;
    }
  } catch (erro) {
    mostrarAviso('aviso-calculadora', `Não foi possível corrigir: ${erro.message}`);
  }
}

/* ---------------------------------- inicio -------------------------------- */

function ligarFiltros() {
  const filtros = document.getElementById('filtros-periodo');
  if (!filtros) return;

  filtros.addEventListener('click', (evento) => {
    const alvo = evento.target.closest('.chip');
    if (!alvo) return;

    Array.from(filtros.querySelectorAll('.chip')).forEach((chip) => chip.classList.remove('is-ativo'));
    alvo.classList.add('is-ativo');
    anosSelecionados = Number(alvo.dataset.anos) || 0;
    carregarComparativo();
  });
}

async function iniciar() {
  const final = document.getElementById('calc-final');
  if (final) final.value = new Date().toISOString().slice(0, 10);

  const formulario = document.getElementById('formulario-calculadora');
  if (formulario) formulario.addEventListener('submit', corrigirValor);

  const botao = document.getElementById('botao-atualizar');
  if (botao) botao.addEventListener('click', dispararAtualizacao);

  ligarFiltros();
  const estado = await carregarStatus();

  try {
    await carregarResumo();
  } catch (erro) {
    mostrarAviso('aviso-grafico', `Resumo indisponível: ${erro.message}`);
  }

  await carregarComparativo();

  // Se uma coleta já estava rodando (outra aba, por exemplo), acompanha desde já.
  if (estado && estado.coleta && estado.coleta.em_andamento) {
    const botao = document.getElementById('botao-atualizar');
    if (botao) botao.disabled = true;
    acompanharColeta().then(() => Promise.all([carregarResumo(), carregarComparativo(), carregarStatus()]))
      .finally(() => { if (botao) { botao.disabled = false; botao.textContent = 'Atualizar'; } });
  }
}

document.addEventListener('DOMContentLoaded', iniciar);
