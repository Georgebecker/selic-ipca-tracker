#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verificar_iteracao.py — ferramenta de apoio do Loop Engineering.

O que faz:
  - roda os comandos de verificação definidos em config_loop.json;
  - mede a métrica principal (comando + expressão regular);
  - compara com o melhor valor registrado em baseline.json;
  - sugere a decisão (ACEITO ou REJEITADO) e grava um relatório em outputs/.

O que NÃO faz:
  - não altera o código do workspace (quem aplica e reverte é o agente);
  - não decide sozinho: a decisão final é registrada no passo "registrar".

Uso:
  python verificar_iteracao.py estado
  python verificar_iteracao.py medir [--definir-baseline]
  python verificar_iteracao.py verificar --hipotese "texto da hipótese"
  python verificar_iteracao.py registrar --decisao ACEITO|REJEITADO --hipotese "texto" [--relatorio ARQUIVO] [--arquivos "a,b,c"]

Códigos de saída do "verificar":
  0 = candidato a ACEITO (comandos passaram e métrica melhorou)
  2 = candidato a REJEITADO (comando falhou ou métrica não melhorou)
  1 = erro de configuração ou de execução

Sem emojis de propósito: compatibilidade com o console do Windows.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

RAIZ = Path(__file__).resolve().parent
ARQ_CONFIG = RAIZ / "config_loop.json"
ARQ_BASELINE = RAIZ / "baseline.json"
ARQ_LOG = RAIZ / "log.md"
DIR_SAIDA = RAIZ / "outputs"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def falhar(mensagem: str, codigo: int = 1) -> NoReturn:
    print("")
    print("[erro] " + mensagem)
    raise SystemExit(codigo)


def avisar(mensagem: str) -> None:
    print("[aviso] " + mensagem)


def info(mensagem: str) -> None:
    print(mensagem)


def carregar_json(caminho: Path, rotulo: str) -> dict:
    if not caminho.exists():
        falhar("não encontrei o arquivo " + caminho.name + " (" + rotulo + ").", 1)

    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        falhar(
            "o arquivo " + caminho.name + " tem um erro de formato na linha "
            + str(erro.lineno) + ": " + erro.msg,
            1,
        )


def salvar_json(caminho: Path, dados: dict) -> None:
    caminho.write_text(
        json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def carregar_config() -> dict:
    return carregar_json(ARQ_CONFIG, "configuração de máquina do Loop")


def carregar_baseline() -> dict:
    return carregar_json(ARQ_BASELINE, "linha de base das métricas")


def diretorio_de_trabalho(config: dict) -> Path:
    relativo = config.get("verificacao", {}).get("diretorio_de_trabalho", "workspace")
    return (RAIZ / relativo).resolve()


def caminho_legivel(caminho: Path) -> str:
    try:
        return caminho.relative_to(RAIZ).as_posix()
    except ValueError:
        return str(caminho)


def menor_e_melhor(config: dict) -> bool:
    return str(config.get("metrica", {}).get("direcao", "menor_melhor")) != "maior_melhor"


def formatar_numero(valor) -> str:
    if valor is None:
        return "(sem valor)"
    try:
        return ("%.4f" % float(valor)).rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(valor)


def formatar_codigo(codigo) -> str:
    """Converte o código de saída do Windows (sem sinal) no valor legível."""
    if codigo is None:
        return "sem código"
    valor = int(codigo)
    if valor > 2147483647:
        valor -= 4294967296
    return str(valor)


def validar_config(config: dict) -> list:
    problemas = []
    verificacao = config.get("verificacao", {})
    metrica = config.get("metrica", {})

    comandos = verificacao.get("comandos")
    if not isinstance(comandos, list):
        problemas.append("verificacao.comandos precisa ser uma lista de comandos")
    elif not comandos:
        problemas.append("nenhum comando de verificação definido em verificacao.comandos")
    else:
        for comando in comandos:
            if not isinstance(comando, str) or not comando.strip():
                problemas.append("verificacao.comandos contém um item vazio ou inválido")

    if not metrica.get("comando"):
        problemas.append("metrica.comando está vazio (como medir a métrica?)")

    expressao = metrica.get("regex")
    if not expressao:
        problemas.append("metrica.regex está vazio (como extrair o número da saída?)")
    else:
        try:
            compilada = re.compile(expressao)
            if compilada.groups < 1:
                problemas.append(
                    "metrica.regex precisa ter pelo menos um grupo de captura, ex.: ([0-9.]+)"
                )
        except re.error as erro:
            problemas.append("metrica.regex inválida: " + str(erro))

    return problemas


def falhar_se_config_invalida(config: dict) -> None:
    problemas = validar_config(config)
    if problemas:
        texto = "a configuração precisa de ajustes antes de continuar:\n"
        for problema in problemas:
            texto += "  - " + problema + "\n"
        texto += "edite o arquivo config_loop.json."
        falhar(texto.rstrip(), 1)


def decodificar(bruto) -> str:
    if bruto is None:
        return ""
    if isinstance(bruto, str):
        return bruto
    for codificacao in ("utf-8", "cp1252", "latin-1"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return bruto.decode("utf-8", "replace")


def rodar_comando(comando: str, diretorio: Path, timeout: int):
    """Devolve (codigo, saida). codigo = None quando não foi possível executar."""
    try:
        processo = subprocess.run(
            comando,
            shell=True,
            cwd=str(diretorio),
            capture_output=True,
            timeout=timeout,
        )
        saida = decodificar(processo.stdout)
        erro = decodificar(processo.stderr)
        if erro:
            saida = (saida + "\n" if saida else "") + erro
        return processo.returncode, saida
    except subprocess.TimeoutExpired as expirado:
        saida = decodificar(expirado.stdout)
        erro = decodificar(expirado.stderr)
        if erro:
            saida = (saida + "\n" if saida else "") + erro
        return None, saida + "\n[tempo esgotado após " + str(timeout) + " segundos]"
    except OSError as erro:
        return None, "[não foi possível executar o comando: " + str(erro) + "]"


def ultimas_linhas(texto: str, quantidade: int = 15) -> str:
    linhas = (texto or "").rstrip().splitlines()
    if len(linhas) <= quantidade:
        return "\n".join(linhas)
    return "\n".join(linhas[-quantidade:])


def extrair_valor(texto: str, metrica: dict):
    """Devolve (valor, problema). valor é float ou None."""
    expressao_texto = metrica.get("regex") or ""
    if not expressao_texto:
        return None, "metrica.regex não está definida em config_loop.json"

    try:
        expressao = re.compile(expressao_texto)
    except re.error as erro:
        return None, "metrica.regex é inválida: " + str(erro)

    encontrado = expressao.search(texto or "")
    if not encontrado:
        return None, "a expressão regular não encontrou o valor na saída do comando de medição"

    grupo = metrica.get("grupo")
    try:
        if expressao.groups >= 1:
            numero_grupo = int(grupo) if grupo is not None else 1
            bruto = encontrado.group(numero_grupo)
        else:
            bruto = encontrado.group(0)
    except (IndexError, ValueError):
        return None, "o grupo de captura configurado não existe na expressão regular"

    bruto = str(bruto).strip()
    try:
        return float(bruto), None
    except ValueError:
        try:
            return float(bruto.replace(",", ".")), None
        except ValueError:
            return None, "o valor extraído não é um número: " + bruto


def comparar(novo, referencia, menor_melhor: bool) -> bool:
    if referencia is None:
        return True
    if novo == referencia:
        return False
    return novo < referencia if menor_melhor else novo > referencia


def variacao_percentual(antes, depois, menor_melhor: bool) -> float:
    if not antes:
        return 0.0
    if menor_melhor:
        return (antes - depois) / antes * 100.0
    return (depois - antes) / antes * 100.0


def calcular_alvo(valor_inicial, meta_percentual, menor_melhor: bool):
    if valor_inicial is None or not meta_percentual:
        return None
    fator = (1 - meta_percentual / 100.0) if menor_melhor else (1 + meta_percentual / 100.0)
    return valor_inicial * fator


def meta_foi_atingida(valor, valor_inicial, meta_percentual, menor_melhor: bool) -> bool:
    alvo = calcular_alvo(valor_inicial, meta_percentual, menor_melhor)
    if valor is None or alvo is None:
        return False
    if menor_melhor:
        return valor <= alvo + 1e-9
    return valor >= alvo - 1e-9


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_estado(_args) -> int:
    config = carregar_config()
    baseline = carregar_baseline()
    metrica = config.get("metrica", {})
    regra_menor = menor_e_melhor(config)

    info("Loop Engineering — estado")
    info("=" * 42)
    info("Métrica principal: " + str(metrica.get("nome", "(sem nome)"))
         + " (" + str(metrica.get("unidade", "sem unidade")) + ")")
    info("Direção: " + ("menor é melhor" if regra_menor else "maior é melhor"))

    valor_inicial = baseline.get("valor_inicial")
    melhor_valor = baseline.get("melhor_valor")
    meta_percentual = baseline.get("meta_percentual")

    if melhor_valor is None:
        info("")
        info("Ainda não existe valor medido (linha de base vazia).")
        info("Próximo passo: python verificar_iteracao.py medir --definir-baseline")
    else:
        alvo = calcular_alvo(valor_inicial, meta_percentual, regra_menor)
        info("Valor inicial: " + formatar_numero(valor_inicial)
             + " | Melhor valor: " + formatar_numero(melhor_valor))
        if alvo is not None:
            progresso_meta = variacao_percentual(valor_inicial, melhor_valor, regra_menor)
            info("Meta: " + formatar_numero(meta_percentual) + "% -> alvo "
                 + formatar_numero(alvo) + " | progresso: " + ("%.1f" % progresso_meta) + "%")
        historico = baseline.get("historico_de_aceites") or []
        if historico:
            ultimo = historico[-1]
            info("Último aceito: iteração " + str(ultimo.get("iteracao", "?"))
                 + " — " + str(ultimo.get("hipotese", "")))

    progresso = baseline.get("progresso", {})
    info("Iterações: " + str(progresso.get("iteracao_atual", 0))
         + " (aceitos " + str(progresso.get("aceitos", 0))
         + ", rejeitados " + str(progresso.get("rejeitados", 0))
         + ", rejeições seguidas " + str(progresso.get("rejeicoes_consecutivas", 0)) + ")")

    problemas = validar_config(config)
    if problemas:
        info("")
        info("Avisos de configuração:")
        for problema in problemas:
            info("  - " + problema)
    else:
        quantidade = len(config.get("verificacao", {}).get("comandos", []))
        info("Configuração: ok (" + str(quantidade) + " comandos de verificação)")

    pasta = diretorio_de_trabalho(config)
    if not pasta.exists():
        avisar("a pasta de trabalho '" + caminho_legivel(pasta)
               + "' não existe; crie-a e coloque o projeto alvo dentro")

    limites = config.get("limites", {})
    info("Limites: máximo de " + str(limites.get("max_iteracoes", "?"))
         + " iterações; parada com " + str(limites.get("rejeicoes_consecutivas", "?"))
         + " rejeições seguidas")
    return 0


def cmd_medir(args) -> int:
    config = carregar_config()
    baseline = carregar_baseline()
    falhar_se_config_invalida(config)

    metrica = config.get("metrica", {})
    pasta = diretorio_de_trabalho(config)
    if not pasta.exists():
        falhar("a pasta de trabalho '" + str(pasta)
               + "' não existe. Crie-a e coloque o projeto alvo dentro dela.", 1)

    timeout = int(config.get("verificacao", {}).get("timeout_segundos", 900))
    comando = str(metrica.get("comando"))
    info("Medindo a métrica: " + comando)
    codigo, saida = rodar_comando(comando, pasta, timeout)

    pasta_medicoes = DIR_SAIDA / "medicoes"
    pasta_medicoes.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo_saida = pasta_medicoes / ("medicao_" + carimbo + ".txt")
    arquivo_saida.write_text("$ " + comando + "\n\n" + saida, encoding="utf-8")

    if codigo != 0:
        info("")
        avisar("o comando de medição falhou"
               + ("" if codigo is None else " (código " + formatar_codigo(codigo) + ")"))
        info("Últimas linhas da saída:")
        info(ultimas_linhas(saida))
        falhar("verifique o comando em config_loop.json e o projeto dentro de workspace/. "
               + "Saída completa: " + caminho_legivel(arquivo_saida), 1)

    valor, problema = extrair_valor(saida, metrica)
    if valor is None:
        info("Últimas linhas da saída:")
        info(ultimas_linhas(saida))
        falhar("não consegui ler o número da métrica. " + str(problema)
               + ". Saída completa: " + caminho_legivel(arquivo_saida), 1)

    unidade = str(metrica.get("unidade", "") or "")
    sufixo_unidade = (" " + unidade) if unidade else ""
    info("Valor medido: " + formatar_numero(valor) + sufixo_unidade)

    if args.definir_baseline:
        if baseline.get("valor_inicial") is None and baseline.get("melhor_valor") is None:
            baseline["valor_inicial"] = valor
            baseline["melhor_valor"] = valor
            baseline["atualizado_em"] = agora_iso()
            salvar_json(ARQ_BASELINE, baseline)
            info("")
            info("Linha de base definida: " + formatar_numero(valor) + sufixo_unidade)
        else:
            info("")
            avisar("já existe uma linha de base (melhor valor = "
                   + formatar_numero(baseline.get("melhor_valor"))
                   + "); nada foi alterado. Use 'verificar' para comparar uma mudança.")
    else:
        info("(dica) para gravar este valor como linha de base inicial, "
             "rode de novo com --definir-baseline")

    return 0


def cmd_verificar(args) -> int:
    config = carregar_config()
    baseline = carregar_baseline()
    falhar_se_config_invalida(config)

    metrica = config.get("metrica", {})
    regra_menor = menor_e_melhor(config)

    valor_antes = baseline.get("melhor_valor")
    if valor_antes is None:
        falhar("ainda não existe linha de base. Rode primeiro:\n"
               "    python verificar_iteracao.py medir --definir-baseline", 1)

    pasta = diretorio_de_trabalho(config)
    if not pasta.exists():
        falhar("a pasta de trabalho '" + str(pasta)
               + "' não existe. Crie-a e coloque o projeto alvo dentro dela.", 1)

    verificacao = config.get("verificacao", {})
    comandos = verificacao.get("comandos", [])
    parar_no_primeiro = bool(verificacao.get("parar_no_primeiro_erro", True))
    timeout = int(verificacao.get("timeout_segundos", 900))

    numero_iteracao = int(baseline.get("progresso", {}).get("iteracao_atual", 0)) + 1
    pasta_iteracao = DIR_SAIDA / ("iteracao_" + ("%06d" % numero_iteracao))
    pasta_iteracao.mkdir(parents=True, exist_ok=True)
    iniciado_em = agora_iso()

    info("Iteração " + str(numero_iteracao) + " — hipótese: " + args.hipotese)
    info("-" * 42)

    resultados = []
    saidas = {}
    for indice, comando in enumerate(comandos, start=1):
        info("  [" + str(indice) + "/" + str(len(comandos)) + "] " + comando + " ...")
        codigo, saida = rodar_comando(comando, pasta, timeout)
        passou = codigo == 0
        info("      -> " + ("OK" if passou else
                            ("FALHOU" + ("" if codigo is None else " (código " + formatar_codigo(codigo) + ")"))))
        arquivo = pasta_iteracao / ("comando_" + ("%02d" % indice) + ".txt")
        arquivo.write_text("$ " + comando + "\n\n" + saida, encoding="utf-8")
        resultados.append({
            "comando": comando,
            "codigo": codigo,
            "passou": passou,
            "arquivo": caminho_legivel(arquivo),
        })
        saidas[comando] = (passou, saida)
        if not passou and parar_no_primeiro:
            break

    comandos_ok = len(resultados) == len(comandos) and all(r["passou"] for r in resultados)

    valor_depois = None
    melhoria = None
    problema_medicao = None
    meta_atingida = False

    if comandos_ok:
        comando_metrica = str(metrica.get("comando", ""))
        saida_metrica = None
        guardado = saidas.get(comando_metrica)
        if guardado is not None and guardado[0]:
            saida_metrica = guardado[1]
            info("  Medindo a métrica (reaproveitando a saída de: " + comando_metrica + ")")
        else:
            info("  Medindo a métrica: " + comando_metrica)
            codigo_metrica, saida_metrica = rodar_comando(comando_metrica, pasta, timeout)
            arquivo_metrica = pasta_iteracao / "metrica.txt"
            arquivo_metrica.write_text("$ " + comando_metrica + "\n\n" + saida_metrica,
                                       encoding="utf-8")
            if codigo_metrica != 0:
                problema_medicao = ("o comando de medição falhou"
                                    + ("" if codigo_metrica is None
                                       else " (código " + formatar_codigo(codigo_metrica) + ")"))
                info("      -> FALHOU")
        if problema_medicao is None and saida_metrica is not None:
            valor_depois, problema = extrair_valor(saida_metrica, metrica)
            if valor_depois is None:
                problema_medicao = str(problema)
            else:
                info("      -> " + formatar_numero(valor_depois)
                     + (" " + str(metrica.get("unidade")) if metrica.get("unidade") else ""))

    melhorou = False
    if valor_depois is not None:
        melhoria = variacao_percentual(valor_antes, valor_depois, regra_menor)
        melhorou = comparar(valor_depois, valor_antes, regra_menor)
        meta_atingida = meta_foi_atingida(valor_depois, baseline.get("valor_inicial"),
                                          baseline.get("meta_percentual"), regra_menor)

    decisao = "ACEITO" if (comandos_ok and melhorou) else "REJEITADO"

    motivos = []
    if not comandos_ok:
        falhos = [r["comando"] for r in resultados if not r["passou"]]
        motivos.append("comando(s) de verificação falharam: " + "; ".join(falhos))
    if problema_medicao:
        motivos.append("não foi possível medir a métrica: " + problema_medicao)
    if comandos_ok and valor_depois is not None and not melhorou:
        motivos.append("a métrica não melhorou (antes " + formatar_numero(valor_antes)
                       + " -> depois " + formatar_numero(valor_depois) + ")")
    if comandos_ok and melhorou:
        motivos.append("todos os comandos passaram e a métrica melhorou "
                       + ("%.2f" % melhoria) + "%")
    if meta_atingida:
        motivos.append("meta do contrato atingida")
    if not motivos:
        motivos.append("sem detalhes")

    relatorio = {
        "iteracao": numero_iteracao,
        "hipotese": args.hipotese,
        "iniciado_em": iniciado_em,
        "terminado_em": agora_iso(),
        "comandos": resultados,
        "comandos_passaram": comandos_ok,
        "metrica": {
            "nome": metrica.get("nome"),
            "unidade": metrica.get("unidade"),
            "antes": valor_antes,
            "depois": valor_depois,
            "melhorou": melhorou,
            "melhoria_percentual": round(melhoria, 4) if melhoria is not None else None,
            "meta_atingida": meta_atingida,
        },
        "decisao_sugerida": decisao,
        "motivos": motivos,
        "arquivos_alterados": [],
        "resumo": {
            "iteration": numero_iteracao,
            "hypothesis": args.hipotese,
            "files_changed": [],
            "metric_before": valor_antes,
            "metric_after": valor_depois,
            "improvement_percent": round(melhoria, 2) if melhoria is not None else None,
            "commands_passed": comandos_ok,
            "decision": "ACCEPTED" if decisao == "ACEITO" else "REJECTED",
            "timestamp": agora_iso(),
        },
    }
    arquivo_relatorio = pasta_iteracao / "relatorio.json"
    salvar_json(arquivo_relatorio, relatorio)
    caminho_relatorio = caminho_legivel(arquivo_relatorio)

    info("")
    info("Resultado da iteração " + str(numero_iteracao) + ":")
    info("  Comandos: " + ("todos passaram" if comandos_ok else "falhou"))
    linha_metrica = "  Métrica: " + formatar_numero(valor_antes)
    if valor_depois is not None:
        linha_metrica += " -> " + formatar_numero(valor_depois)
        if melhoria is not None:
            linha_metrica += " (melhoria de " + ("%.2f" % melhoria) + "%)"
    else:
        linha_metrica += " -> não medida"
    info(linha_metrica)
    if meta_atingida:
        info("  Meta atingida.")
    info("  Decisão sugerida: " + decisao)
    for motivo in motivos:
        info("    - " + motivo)
    info("  Relatório: " + caminho_relatorio)
    info("")
    info("Próximo passo:")
    if decisao == "ACEITO":
        info("  mantenha a mudança e registre:")
    else:
        info("  reverta a mudança no código e registre:")
    info("    python verificar_iteracao.py registrar --decisao " + decisao
         + ' --hipotese "' + args.hipotese + '" --relatorio "' + caminho_relatorio + '"')

    return 0 if decisao == "ACEITO" else 2


def localizar_ultimo_relatorio():
    if not DIR_SAIDA.exists():
        return None
    candidatos = sorted(DIR_SAIDA.glob("iteracao_*/relatorio.json"))
    if not candidatos:
        return None
    return candidatos[-1]


def cmd_registrar(args) -> int:
    baseline = carregar_baseline()

    if args.relatorio:
        caminho = Path(args.relatorio)
        if not caminho.is_absolute():
            possivel = RAIZ / caminho
            if possivel.exists():
                caminho = possivel
        if not caminho.exists():
            falhar("não encontrei o relatório '" + str(args.relatorio) + "'.", 1)
    else:
        caminho = localizar_ultimo_relatorio()
        if caminho is None:
            falhar("nenhum relatório encontrado em outputs/. "
                   "Rode primeiro o comando 'verificar'.", 1)

    relatorio = carregar_json(caminho, "relatório da iteração")

    progresso = baseline.setdefault("progresso", {})
    iteracao_atual = int(progresso.get("iteracao_atual", 0))
    numero_iteracao = int(relatorio.get("iteracao") or (iteracao_atual + 1))
    if numero_iteracao <= iteracao_atual:
        falhar("a iteração " + str(numero_iteracao) + " deste relatório já foi registrada "
               + "(iteração atual = " + str(iteracao_atual) + "). Nada foi alterado.", 1)

    hipotese = args.hipotese or relatorio.get("hipotese") or "(não informada)"
    decisao = args.decisao
    metrica_relatorio = relatorio.get("metrica", {}) or {}
    antes = metrica_relatorio.get("antes")
    depois = metrica_relatorio.get("depois")
    unidade = str(metrica_relatorio.get("unidade") or "")
    sufixo_unidade = (" " + unidade) if unidade else ""
    melhoria = metrica_relatorio.get("melhoria_percentual")
    comandos_passaram = bool(relatorio.get("comandos_passaram"))

    sugestao = relatorio.get("decisao_sugerida")
    if sugestao and sugestao != decisao:
        avisar("o verificador sugeriu " + str(sugestao) + ", mas você registrou " + decisao
               + " — a decisão registrada é a sua.")
    if decisao == "ACEITO" and not comandos_passaram:
        avisar("o relatório indica que nem todos os comandos passaram; "
               "registrando ACEITO mesmo assim (decisão sua).")

    arquivos = args.arquivos.strip() if args.arquivos else ", ".join(
        relatorio.get("arquivos_alterados") or [])
    if not arquivos:
        arquivos = "não informado"

    linhas = [
        "## Iteração " + str(numero_iteracao),
        "- **Hipótese**: " + str(hipotese),
        "- **Arquivos alterados**: " + arquivos,
        "- **Métrica antes**: " + (formatar_numero(antes) + sufixo_unidade
                                   if antes is not None else "não medida"),
        "- **Métrica depois**: " + (formatar_numero(depois) + sufixo_unidade
                                    if depois is not None else "não medida"),
        "- **Melhoria**: " + (("%.2f" % melhoria) + "%" if melhoria is not None else "não medida"),
        "- **Comandos passaram**: " + ("Sim" if comandos_passaram else "Não"),
        "- **Decisão**: " + decisao,
        "- **Data/hora**: " + agora_iso(),
        "",
    ]

    if ARQ_LOG.exists():
        texto_log = ARQ_LOG.read_text(encoding="utf-8")
    else:
        texto_log = "# Log de Iterações — Loop Engineering\n"
    if not texto_log.endswith("\n"):
        texto_log += "\n"
    ARQ_LOG.write_text(texto_log + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")

    progresso["iteracao_atual"] = numero_iteracao
    if decisao == "ACEITO":
        progresso["aceitos"] = int(progresso.get("aceitos", 0)) + 1
        progresso["rejeicoes_consecutivas"] = 0
        if depois is not None:
            baseline["melhor_valor"] = depois
            if baseline.get("valor_inicial") is None and antes is not None:
                baseline["valor_inicial"] = antes
            historico = baseline.setdefault("historico_de_aceites", [])
            historico.append({
                "iteracao": numero_iteracao,
                "hipotese": str(hipotese),
                "valor": depois,
                "variacao_percentual": melhoria,
                "data": agora_iso(),
            })
    else:
        progresso["rejeitados"] = int(progresso.get("rejeitados", 0)) + 1
        progresso["rejeicoes_consecutivas"] = int(progresso.get("rejeicoes_consecutivas", 0)) + 1
    baseline["atualizado_em"] = agora_iso()
    salvar_json(ARQ_BASELINE, baseline)

    info("")
    info("Registrado: iteração " + str(numero_iteracao) + " — " + decisao)
    info("  log.md atualizado")
    if decisao == "ACEITO" and depois is not None:
        info("  baseline.json atualizado: melhor valor = "
             + formatar_numero(depois) + sufixo_unidade)
    if decisao == "REJEITADO":
        info("")
        info("Lembrete: reverta a mudança no código antes da próxima iteração "
             "(ex.: git checkout -- .).")

    config = carregar_config()
    limites = config.get("limites", {})
    avisos_parada = []
    if meta_foi_atingida(baseline.get("melhor_valor"), baseline.get("valor_inicial"),
                         baseline.get("meta_percentual"), menor_e_melhor(config)):
        avisos_parada.append("meta atingida")

    max_iteracoes = limites.get("max_iteracoes")
    if isinstance(max_iteracoes, int) and progresso["iteracao_atual"] >= max_iteracoes:
        avisos_parada.append("limite de " + str(max_iteracoes) + " iterações atingido")

    limite_rejeicoes = limites.get("rejeicoes_consecutivas")
    if (isinstance(limite_rejeicoes, int)
            and progresso["rejeicoes_consecutivas"] >= limite_rejeicoes):
        avisos_parada.append(str(progresso["rejeicoes_consecutivas"])
                             + " rejeições seguidas — pare e revise as hipóteses")

    if avisos_parada:
        info("")
        for aviso in avisos_parada:
            info("[PARADA RECOMENDADA] " + aviso)

    return 0


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def main() -> int:
    analisador = argparse.ArgumentParser(
        description="Ferramenta de verificação do Loop Engineering "
                    "(testa, mede e sugere a decisão)."
    )
    subcomandos = analisador.add_subparsers(dest="subcomando")

    subcomandos.add_parser("estado", help="mostra a situação atual: métrica, progresso e limites")

    p_medir = subcomandos.add_parser("medir", help="mede a métrica principal agora")
    p_medir.add_argument("--definir-baseline", action="store_true",
                         help="grava o valor medido como linha de base inicial (baseline.json)")

    p_verificar = subcomandos.add_parser(
        "verificar", help="roda os comandos, mede a métrica e sugere a decisão")
    p_verificar.add_argument("--hipotese", required=True,
                             help="texto curto da hipótese desta iteração")

    p_registrar = subcomandos.add_parser(
        "registrar", help="grava a decisão no log.md e atualiza o baseline.json")
    p_registrar.add_argument("--decisao", required=True, choices=["ACEITO", "REJEITADO"],
                             help="decisão final da iteração")
    p_registrar.add_argument("--hipotese", default="",
                             help="texto da hipótese (padrão: o do relatório)")
    p_registrar.add_argument("--relatorio", default="",
                             help="caminho do relatório (padrão: o último gerado)")
    p_registrar.add_argument("--arquivos", default="",
                             help='lista de arquivos alterados (ex.: "a.py, b.py")')

    argumentos = analisador.parse_args()

    if not argumentos.subcomando:
        analisador.print_help()
        return 0

    if argumentos.subcomando == "estado":
        return cmd_estado(argumentos)
    if argumentos.subcomando == "medir":
        return cmd_medir(argumentos)
    if argumentos.subcomando == "verificar":
        return cmd_verificar(argumentos)
    if argumentos.subcomando == "registrar":
        return cmd_registrar(argumentos)

    analisador.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
