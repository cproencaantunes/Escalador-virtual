"""
Orquestrador principal.

Fluxo:
  1. Ler payload JSON do Apps Script
  2. Validar restrições LN (output Gemini)
  3. Correr alocação Hungarian + macro/micro
  4. Escrever anestesistas na Proposta Semana via Sheets API
  5. Guardar resultado JSON (artefacto GitHub Actions)

Payload esperado:
{
  "semana": "2026-04-07",
  "spreadsheet_id": "ID_COORDENADOR",
  "blocos": [{
    "id": "B0",
    "hcis": "2341887",
    "sala": "A0",
    "cir": "LUIS BRANDAO",
    "dia": 0,
    "iniMin": 840,
    "fimMin": 960,
    "tIdx": 1,
    "tSlots": [1],
    "oIni": 10,
    "oFim": 13,
    "colAne": 80,
    "semAne": false
  }],
  "disponibilidades": {
    "MM": {"slots": [true,false,...], "obs": null, "fixa": false}
  },
  "afinidades": {
    "MM": {"1": [{"cir":"LUIS BRANDAO","n":44,"pct":82}]}
  },
  "equipas": [["NELSON SILVA","LUIS GALINDO",44]],
  "restricoes": [
    {"ane":"JN","tipo":"fixar","slot":1,"razao":"Gastro Seg-T"}
  ]
}
"""

import argparse, json, sys, traceback
from collections import defaultdict

from hungarian import alocar
from restricoes import validar
from sheets_client import escrever_batch, col_letra

ABA_PROPOSTA = "Proposta Semana"
LINHA_DADOS  = 3
LINHAS_DIA   = 33


def linha_prop(dia: int, off: int) -> int:
    return LINHA_DADOS + dia * LINHAS_DIA + off


def escrever_alocacoes(spreadsheet_id: str, blocos: list, alocacoes: list,
                       equipas: list):
    """
    Escreve anestesistas na Proposta.
    Regra: equipa partilhada → só a sala principal (primeira do grupo) recebe a sigla.
    """
    aloc_map = {a["id"]: a for a in alocacoes}

    # Identificar equipas para aplicar regra "só numa sala"
    equipa_de: dict[str, str] = {}
    for i, par in enumerate(equipas):
        eq_id = f"EQ{i}"
        for cir in par[:2]:
            equipa_de[cir.upper()] = eq_id

    # Para cada equipa+dia, a sala "principal" é a que tem o bloco mais cedo
    sala_principal: dict[tuple, str] = {}  # (eq_id, dia) → sala
    for b in sorted(blocos, key=lambda x: x["iniMin"]):
        cir_u = b["cir"].upper()
        eq_id = equipa_de.get(cir_u)
        if eq_id:
            chave = (eq_id, b["dia"])
            if chave not in sala_principal:
                sala_principal[chave] = b["sala"]

    # Limpar colunas de anestesista (todas as salas, todos os dias)
    colunas_ane = sorted({b["colAne"] for b in blocos})
    updates_limpar = []
    for col in colunas_ane:
        for dia in range(5):
            for off in range(LINHAS_DIA):
                linha = linha_prop(dia, off)
                updates_limpar.append({
                    "range": f"'{ABA_PROPOSTA}'!{col_letra(col)}{linha}",
                    "values": [[""]]
                })
    escrever_batch(spreadsheet_id, updates_limpar)

    # Escrever anestesistas
    updates = []
    for b in blocos:
        aloc = aloc_map.get(b["id"])
        if not aloc or not aloc.get("ane"):
            continue
        ane   = aloc["ane"]
        cir_u = b["cir"].upper()
        eq_id = equipa_de.get(cir_u)

        # Regra equipa: só escrever na sala principal
        if eq_id:
            chave = (eq_id, b["dia"])
            if sala_principal.get(chave) != b["sala"]:
                continue  # sala secundária — fica vazia

        for off in range(b["oIni"], b["oFim"] + 1):
            linha = linha_prop(b["dia"], off)
            updates.append({
                "range": f"'{ABA_PROPOSTA}'!{col_letra(b['colAne'])}{linha}",
                "values": [[ane]]
            })

    escrever_batch(spreadsheet_id, updates)
    n_escritos = sum(1 for a in alocacoes if a.get("ane"))
    print(f"  Escritos: {n_escritos} anestesistas na Proposta")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    parser.add_argument("--output",  required=True)
    args = parser.parse_args()

    with open(args.payload, encoding="utf-8") as f:
        payload = json.load(f)

    semana         = payload.get("semana","")
    ss_id          = payload.get("spreadsheet_id","")
    blocos         = payload.get("blocos",[])
    disps          = payload.get("disponibilidades",{})
    afinidades     = payload.get("afinidades",{})
    equipas        = payload.get("equipas",[])
    restricoes_raw = payload.get("restricoes",[])

    print(f"Semana: {semana} | Blocos: {len(blocos)} | Anes: {len(disps)}")

    # Validar restrições
    restricoes, avisos = validar(restricoes_raw, set(disps.keys()))
    for av in avisos:
        print(f"  AVISO: {av}")

    # Alocar
    print("A alocar...")
    alocacoes = alocar(blocos, disps, afinidades, equipas, restricoes)

    n_ok  = sum(1 for a in alocacoes if a.get("ane"))
    n_sem = sum(1 for a in alocacoes if not a.get("ane"))
    print(f"  Alocados: {n_ok} | Sem cobertura: {n_sem}")

    # Escrever na Proposta
    if ss_id:
        print(f"A escrever na Proposta...")
        try:
            escrever_alocacoes(ss_id, blocos, alocacoes, equipas)
        except Exception as e:
            print(f"  ERRO Sheets: {e}")
            traceback.print_exc()

    # Guardar resultado
    resultado = {
        "semana": semana,
        "alocacoes": alocacoes,
        "stats": {"total": len(alocacoes), "alocados": n_ok, "sem_cobertura": n_sem},
        "avisos": avisos,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"Resultado: {args.output}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERRO FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
