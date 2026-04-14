"""
Alocação de anestesistas — lógica micro/macro com disponibilidades horárias.

disponibilidades_horas: {sigla: {dia: [slots_minutos]}}
  dia = "Seg"/"Ter"/"Qua"/"Qui"/"Sex"
  slots = múltiplos de 30 (450=7:30, 480=8:00, ..., 1410=23:30)
"""

from collections import defaultdict

DIAS_STR  = ["Seg","Ter","Qua","Qui","Sex"]
TURNO_L   = ["Seg-M","Seg-T","Ter-M","Ter-T","Qua-M","Qua-T","Qui-M","Qui-T","Sex-M","Sex-T"]
INTERVALO_MIN = 30


# ---------------------------------------------------------------------------
# Utilitários temporais
# ---------------------------------------------------------------------------

def slots_bloco(iniMin: int, fimMin: int) -> set:
    """Slots de 30min cobertos pelo bloco [iniMin, fimMin[."""
    return set(range((iniMin // 30) * 30, fimMin, 30))


def sobreposicao(a_ini, a_fim, b_ini, b_fim) -> bool:
    return a_ini < b_fim and b_ini < a_fim


def compativel_temporal(blocoA: dict, blocoB: dict, mesma_equipa: bool) -> bool:
    if mesma_equipa:
        return True
    a_ini, a_fim = blocoA["iniMin"], blocoA["fimMin"]
    b_ini, b_fim = blocoB["iniMin"], blocoB["fimMin"]
    if sobreposicao(a_ini, a_fim, b_ini, b_fim):
        return False
    if a_fim <= b_ini:
        return b_ini >= a_fim + INTERVALO_MIN
    else:
        return a_ini >= b_fim + INTERVALO_MIN


# ---------------------------------------------------------------------------
# Afinidade histórica
# ---------------------------------------------------------------------------

def afinidade(ane: str, cir: str, tIdx: int, afinidades: dict) -> float:
    dados = afinidades.get(ane, {}).get(str(tIdx), [])
    cir_u = cir.upper()
    best = 0.0
    for e in dados:
        nome = e.get("cir","").upper()
        pct  = float(e.get("pct", 0))
        if nome == cir_u:
            return pct
        palavras = [p for p in cir_u.split() if len(p) > 2]
        hits = sum(1 for p in palavras if p in nome)
        if hits >= max(1, len(palavras) // 2):
            best = max(best, pct * 0.8)
    return best


# ---------------------------------------------------------------------------
# Disponibilidade horária
# ---------------------------------------------------------------------------

def ane_disponivel_bloco(ane: str, bloco: dict, disp_horas: dict) -> bool:
    """Verifica se ane tem todos os slots do bloco disponíveis."""
    dia_str = DIAS_STR[bloco["dia"]]
    slots_ane = set(disp_horas.get(ane, {}).get(dia_str, []))
    if not slots_ane:
        return False
    slots_b = slots_bloco(bloco["iniMin"], bloco["fimMin"])
    return slots_b.issubset(slots_ane)


def ane_disponivel_macro(ane: str, macro: dict, disp_horas: dict) -> tuple:
    """Verifica disponibilidade horária para todos os micro do macro."""
    for b in macro["micro"]:
        if not ane_disponivel_bloco(ane, b, disp_horas):
            dia_str = DIAS_STR[b["dia"]]
            return False, f"indisponível {dia_str} {b['iniMin']//60:02d}:{b['iniMin']%60:02d}"
    return True, "ok"


# ---------------------------------------------------------------------------
# Construção de macros
# ---------------------------------------------------------------------------

def construir_macros(blocos: list, equipas: list) -> list:
    equipa_de: dict[str, str] = {}
    for i, par in enumerate(equipas):
        eq_id = f"EQ{i}"
        for cir in par[:2]:
            equipa_de[cir.upper()] = eq_id

    grupos: dict[tuple, list] = defaultdict(list)
    for b in blocos:
        cir_u = b["cir"].upper()
        eq_id = equipa_de.get(cir_u)
        chave = (eq_id or cir_u, b["dia"], b.get("salaId", b.get("sala", "")))
        grupos[chave].append(b)

    macros = []
    for (eq_ou_cir, dia, sala), micro_list in grupos.items():
        t_slots = sorted(set(s for b in micro_list for s in b.get("tSlots", [b["tIdx"]])))
        cirs = list({b["cir"] for b in micro_list})
        macros.append({
            "id": f"M_{eq_ou_cir}_{dia}_{sala}",
            "cirs": cirs,
            "eq_id": eq_ou_cir if str(eq_ou_cir).startswith("EQ") else None,
            "dia": dia,
            "sala": sala,
            "micro": micro_list,
            "tSlots": t_slots,
        })
    return macros


# ---------------------------------------------------------------------------
# Verificar se ane pode cobrir macro (disponibilidade + restrições + temporal)
# ---------------------------------------------------------------------------

def ane_cobre_macro(ane: str, macro: dict, disp_horas: dict,
                    restricoes_ane: dict, alocacoes_ane: dict,
                    equipas_set: set) -> tuple:

    # 1. Disponibilidade horária
    pode, razao = ane_disponivel_macro(ane, macro, disp_horas)
    if not pode:
        return False, razao

    # 2. Restrições
    for r in restricoes_ane.get(ane, []):
        tipo = r["tipo"]
        slot = r.get("slot")
        if tipo == "so_manha" and any(t % 2 == 1 for t in macro["tSlots"]):
            return False, "só manhã"
        if tipo == "so_tarde" and any(t % 2 == 0 for t in macro["tSlots"]):
            return False, "só tarde"
        if tipo == "excluir" and slot in macro["tSlots"]:
            return False, f"excluído slot {TURNO_L[slot] if slot < len(TURNO_L) else slot}"

    # 3. Compatibilidade temporal com blocos já alocados
    for micro in macro["micro"]:
        for ja in alocacoes_ane.get(ane, []):
            cir_micro = micro["cir"].upper()
            cir_ja    = ja["cir"].upper()
            mesma_eq  = frozenset([cir_micro, cir_ja]) in equipas_set
            if not compativel_temporal(micro, ja, mesma_eq):
                return False, f"conflito temporal com {cir_ja}"

    return True, "ok"


# ---------------------------------------------------------------------------
# Algoritmo principal
# ---------------------------------------------------------------------------

def alocar(blocos: list, disponibilidades_horas: dict, afinidades: dict,
           equipas: list, restricoes: list) -> list:
    """
    blocos               : lista de micro-blocos com iniMin/fimMin/dia/cir
    disponibilidades_horas: {sigla: {dia: [slots_minutos]}}
    afinidades           : {sigla: {tIdx_str: [{cir,n,pct}]}}
    equipas              : [[cir1,cir2,n], ...]
    restricoes           : [{ane,tipo,slot?,razao}]
    """
    anestesistas = sorted(disponibilidades_horas.keys())
    print(f"  Anestesistas: {len(anestesistas)} | Blocos: {len(blocos)}")

    restricoes_ane: dict[str, list] = defaultdict(list)
    for r in restricoes:
        restricoes_ane[r["ane"]].append(r)

    equipas_set: set = {
        frozenset([p[0].upper(), p[1].upper()]) for p in equipas
    }

    macros = construir_macros(blocos, equipas)
    print(f"  Macros: {len(macros)}")

    alocacoes_ane: dict[str, list] = defaultdict(list)
    resultado_map: dict[str, str]  = {}
    razao_map: dict[str, str]      = {}

    macros_ord = sorted(macros, key=lambda m: (-len(m["tSlots"]), m["dia"]))

    for macro in macros_ord:
        # Tentar alocar 1 ane para todo o macro
        candidatos = []
        for ane in anestesistas:
            pode, razao = ane_cobre_macro(
                ane, macro, disponibilidades_horas,
                restricoes_ane, alocacoes_ane, equipas_set
            )
            if pode:
                pcts = [
                    afinidade(ane, cir, t, afinidades)
                    for cir in macro["cirs"]
                    for t in macro["tSlots"]
                ]
                pct_media = sum(pcts) / max(len(pcts), 1)
                bonus = 20 if any(
                    ja["cir"] == b["cir"] and ja["dia"] == b["dia"]
                    for b in macro["micro"]
                    for ja in alocacoes_ane.get(ane, [])
                ) else 0
                custo = max(0, 100 - pct_media - bonus)
                candidatos.append((custo, ane, pct_media))

        if candidatos:
            candidatos.sort()
            _, melhor_ane, pct = candidatos[0]

            # Fixações
            for r in restricoes:
                if r["tipo"] == "fixar" and r.get("slot") in macro["tSlots"]:
                    if r["ane"] in [c[1] for c in candidatos]:
                        melhor_ane = r["ane"]
                        pct = afinidade(melhor_ane, macro["cirs"][0],
                                        macro["tSlots"][0], afinidades)
                        break

            slots_str = "+".join(TURNO_L[t] for t in macro["tSlots"] if t < len(TURNO_L))
            razao = f"afinidade {pct:.0f}% {slots_str}" if pct > 0 else f"disponível {slots_str}"

            for b in macro["micro"]:
                resultado_map[b["id"]] = melhor_ane
                razao_map[b["id"]]     = razao
                alocacoes_ane[melhor_ane].append(b)
            continue

        # Fallback: por turno separado
        por_turno: dict[int, list] = defaultdict(list)
        for b in macro["micro"]:
            for t in b.get("tSlots", [b["tIdx"]]):
                por_turno[t].append(b)

        ane_por_turno: dict[int, str] = {}
        for t in sorted(por_turno.keys()):
            micro_t = por_turno[t]
            macro_t = {**macro, "tSlots": [t], "micro": micro_t}

            preferido = list(ane_por_turno.values())[-1] if ane_por_turno else None
            if preferido:
                pode, _ = ane_cobre_macro(
                    preferido, macro_t, disponibilidades_horas,
                    restricoes_ane, alocacoes_ane, equipas_set
                )
                if pode:
                    for b in micro_t:
                        if b["id"] not in resultado_map:
                            resultado_map[b["id"]] = preferido
                            pct = afinidade(preferido, b["cir"], t, afinidades)
                            razao_map[b["id"]] = f"continuidade {TURNO_L[t] if t < len(TURNO_L) else t} {pct:.0f}%"
                            alocacoes_ane[preferido].append(b)
                    ane_por_turno[t] = preferido
                    continue

            cands_t = []
            for ane in anestesistas:
                if ane == preferido: continue
                pode, _ = ane_cobre_macro(
                    ane, macro_t, disponibilidades_horas,
                    restricoes_ane, alocacoes_ane, equipas_set
                )
                if pode:
                    pct = sum(afinidade(ane, b["cir"], t, afinidades)
                              for b in micro_t) / max(len(micro_t), 1)
                    cands_t.append((100 - pct, ane, pct))

            if cands_t:
                cands_t.sort()
                _, melhor, pct = cands_t[0]
                for b in micro_t:
                    if b["id"] not in resultado_map:
                        resultado_map[b["id"]] = melhor
                        razao_map[b["id"]] = f"afinidade {pct:.0f}% {TURNO_L[t] if t < len(TURNO_L) else t}"
                        alocacoes_ane[melhor].append(b)
                ane_por_turno[t] = melhor
            else:
                for b in micro_t:
                    if b["id"] not in resultado_map:
                        resultado_map[b["id"]] = None
                        razao_map[b["id"]] = f"sem candidato {TURNO_L[t] if t < len(TURNO_L) else t}"

    resultado = []
    alocados = sum(1 for v in resultado_map.values() if v)
    print(f"  Alocados: {alocados}/{len(blocos)}")

    for b in blocos:
        ane   = resultado_map.get(b["id"])
        razao = razao_map.get(b["id"], "não processado")
        resultado.append({"id": b["id"], "ane": ane, "razao": razao})

    return resultado


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

import json
import argparse
import sys
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    parser.add_argument("--output",  required=True)
    args = parser.parse_args()

    with open(args.payload, encoding="utf-8") as f:
        payload = json.load(f)

    blocos                = payload.get("blocos", [])
    disponibilidades_horas = payload.get("disponibilidades_horas", {})
    afinidades            = payload.get("afinidades", {})
    equipas               = payload.get("equipas", [])
    restricoes            = payload.get("restricoes", [])

    if not blocos:
        print("ERRO: nenhum bloco no payload", file=sys.stderr)
        sys.exit(1)

    if not disponibilidades_horas:
        print("ERRO: disponibilidades_horas vazio no payload", file=sys.stderr)
        sys.exit(1)

    print(f"Payload: {len(blocos)} blocos | {len(disponibilidades_horas)} anestesistas")

    resultado = alocar(
        blocos=blocos,
        disponibilidades_horas=disponibilidades_horas,
        afinidades=afinidades,
        equipas=equipas,
        restricoes=restricoes,
    )

    alocados = sum(1 for r in resultado if r.get("ane"))
    sem = len(resultado) - alocados

    output_obj = {
        "alocacoes": resultado,
        "stats": {
            "total": len(resultado),
            "alocados": alocados,
            "sem_cobertura": sem,
        },
        "avisos": [
            r["razao"] for r in resultado
            if not r.get("ane") and r.get("razao")
        ][:20],
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_obj, f, ensure_ascii=False, indent=2)

    print(f"Resultado: {alocados}/{len(resultado)} alocados → {args.output}")


if __name__ == "__main__":
    main()
