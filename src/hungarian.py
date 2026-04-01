"""
Alocação de anestesistas — Hungarian algorithm + lógica micro/macro.

Hierarquia:
  MICRO  = bloco por doente/HCIS — indivisível
  MACRO  = bloco por cirurgião/equipa + dia — preferência de continuidade

Regras hard:
  1. Disponibilidade (slots) — absoluta
  2. Dois postos ao mesmo tempo — proibido
  3. Intervalo mínimo 30min entre salas diferentes (excepto mesma equipa)
  4. Equipas no mesmo dia → mesmo ane (forte)
  5. Doente indivisível — mesmo ane do início ao fim

Regras soft:
  1. Mesmo cirurgião manhã+tarde → mesmo ane (muda só se indisponível tarde)
  2. Afinidade histórica — maximizar
  3. Cruzamento 14-16h → preferência pelo turno de início
"""

import numpy as np
from scipy.optimize import linear_sum_assignment
from collections import defaultdict

TURNO_L = ["Seg-M","Seg-T","Ter-M","Ter-T","Qua-M","Qua-T","Qui-M","Qui-T","Sex-M","Sex-T"]
INTERVALO_MIN = 30  # minutos entre salas diferentes


# ---------------------------------------------------------------------------
# Utilitários temporais
# ---------------------------------------------------------------------------

def sobreposicao(a_ini, a_fim, b_ini, b_fim) -> bool:
    """True se os intervalos se sobrepõem."""
    return a_ini < b_fim and b_ini < a_fim


def compativel_temporal(blocoA: dict, blocoB: dict, mesma_equipa: bool) -> bool:
    """
    Verifica se dois blocos podem ser cobertos pelo mesmo anestesista.
    Baseia-se nos horários do bloco (fimMin do cirurgião na sala).
    """
    if mesma_equipa:
        return True  # equipa partilhada — sem restrição temporal

    a_ini, a_fim = blocoA["iniMin"], blocoA["fimMin"]
    b_ini, b_fim = blocoB["iniMin"], blocoB["fimMin"]

    # Hard: dois postos ao mesmo tempo
    if sobreposicao(a_ini, a_fim, b_ini, b_fim):
        return False

    # Hard: intervalo mínimo 30min entre salas diferentes
    if a_fim <= b_ini:
        return b_ini >= a_fim + INTERVALO_MIN
    else:  # b_fim <= a_ini
        return a_ini >= b_fim + INTERVALO_MIN


# ---------------------------------------------------------------------------
# Afinidade histórica
# ---------------------------------------------------------------------------

def afinidade(ane: str, cir: str, tIdx: int, afinidades: dict) -> float:
    """Percentagem de afinidade histórica ane→cir no turno tIdx."""
    dados = afinidades.get(ane, {}).get(str(tIdx), [])
    cir_u = cir.upper()
    best = 0.0
    for e in dados:
        nome = e.get("cir","").upper()
        pct  = float(e.get("pct", 0))
        if nome == cir_u:
            return pct
        # Match parcial
        palavras = [p for p in cir_u.split() if len(p) > 2]
        hits = sum(1 for p in palavras if p in nome)
        if hits >= max(1, len(palavras) // 2):
            best = max(best, pct * 0.8)
    return best


# ---------------------------------------------------------------------------
# Construção de macros
# ---------------------------------------------------------------------------

def construir_macros(blocos: list, equipas: list) -> list:
    """
    Agrupa blocos micro em macros (cirurgião/equipa + dia).
    Equipas conhecidas são agrupadas no mesmo macro.
    """
    # Mapa de equipa: cir → id_equipa
    equipa_de: dict[str, str] = {}
    for i, par in enumerate(equipas):
        eq_id = f"EQ{i}"
        for cir in par[:2]:
            equipa_de[cir.upper()] = eq_id

    # Agrupar blocos: chave = (equipa_id ou cir_normalizado, dia, sala)
    # Para equipas: usar o equipa_id como chave comum
    grupos: dict[tuple, list] = defaultdict(list)
    for b in blocos:
        cir_u = b["cir"].upper()
        eq_id = equipa_de.get(cir_u)
        chave = (eq_id or cir_u, b["dia"], b["sala"])
        grupos[chave].append(b)

    macros = []
    for (eq_ou_cir, dia, sala), micro_list in grupos.items():
        # Todos os slots cobertos pelos micro deste grupo
        t_slots = sorted(set(s for b in micro_list for s in b.get("tSlots", [b["tIdx"]])))
        # Cirurgiões únicos neste grupo
        cirs = list({b["cir"] for b in micro_list})
        macros.append({
            "id": f"M_{eq_ou_cir}_{dia}_{sala}",
            "cirs": cirs,
            "eq_id": eq_ou_cir if eq_ou_cir.startswith("EQ") else None,
            "dia": dia,
            "sala": sala,
            "micro": micro_list,
            "tSlots": t_slots,
        })
    return macros


# ---------------------------------------------------------------------------
# Verificar se ane pode cobrir macro
# ---------------------------------------------------------------------------

def ane_cobre_macro(ane: str, macro: dict, disponibilidades: dict,
                    restricoes_ane: dict, alocacoes_ane: dict,
                    equipas_set: set) -> tuple[bool, str]:
    """
    Verifica se ane pode cobrir todos os micro de um macro.
    Devolve (pode, razao).
    alocacoes_ane: {ane: [blocos já alocados]}
    equipas_set: set de frozensets de pares de cirurgiões de equipa
    """
    info = disponibilidades.get(ane, {})
    slots_disp = info.get("slots", [False]*10)

    # Verificar disponibilidade para todos os slots do macro
    for t in macro["tSlots"]:
        if not slots_disp[t]:
            return False, f"indisponível slot {TURNO_L[t]}"

    # Verificar restrições
    for r in restricoes_ane.get(ane, []):
        tipo = r["tipo"]
        slot = r.get("slot")
        if tipo == "so_manha" and any(t % 2 == 1 for t in macro["tSlots"]):
            return False, "só manhã"
        if tipo == "so_tarde" and any(t % 2 == 0 for t in macro["tSlots"]):
            return False, "só tarde"
        if tipo == "excluir" and slot in macro["tSlots"]:
            return False, f"excluído slot {TURNO_L[slot]}"

    # Verificar compatibilidade temporal com blocos já alocados
    ja_alocados = alocacoes_ane.get(ane, [])
    for micro in macro["micro"]:
        for ja in ja_alocados:
            # Determinar se são mesma equipa
            cir_micro = micro["cir"].upper()
            cir_ja    = ja["cir"].upper()
            mesma_eq  = frozenset([cir_micro, cir_ja]) in equipas_set
            if not compativel_temporal(micro, ja, mesma_eq):
                return False, f"conflito temporal com {cir_ja}"

    return True, "ok"


# ---------------------------------------------------------------------------
# Algoritmo principal
# ---------------------------------------------------------------------------

def alocar(blocos: list, disponibilidades: dict, afinidades: dict,
           equipas: list, restricoes: list) -> list:
    """
    Parâmetros
    ----------
    blocos          : lista de micro-blocos (por doente/HCIS)
    disponibilidades: {sigla: {slots:[bool×10], obs:str|None, fixa:bool}}
    afinidades      : {sigla: {tIdx_str: [{cir,n,pct}]}}
    equipas         : [[cir1,cir2,n], ...]
    restricoes      : [{ane,tipo,slot?,razao}]

    Devolve
    -------
    [{id, ane, razao}, ...]  — um entry por micro-bloco
    """

    anestesistas = sorted(disponibilidades.keys())

    # Índice de restrições por ane
    restricoes_ane: dict[str, list] = defaultdict(list)
    for r in restricoes:
        restricoes_ane[r["ane"]].append(r)

    # Set de pares de equipa (para compatibilidade temporal)
    equipas_set: set[frozenset] = {
        frozenset([p[0].upper(), p[1].upper()]) for p in equipas
    }

    # Construir macros
    macros = construir_macros(blocos, equipas)
    print(f"  Macros: {len(macros)} | Micro: {len(blocos)}")

    # Alocações já feitas: ane → lista de micro já atribuídos
    alocacoes_ane: dict[str, list] = defaultdict(list)
    # Resultado: micro_id → ane
    resultado_map: dict[str, str] = {}
    # Razões
    razao_map: dict[str, str] = {}

    # --- Ordenar macros por número de slots (mais restritivos primeiro) ---
    macros_ord = sorted(macros, key=lambda m: (-len(m["tSlots"]), m["dia"]))

    for macro in macros_ord:
        micro_ids = [b["id"] for b in macro["micro"]]

        # --- Tentar alocar 1 ane para todo o macro (dia inteiro) ---
        candidatos = []
        for ane in anestesistas:
            pode, razao = ane_cobre_macro(
                ane, macro, disponibilidades, restricoes_ane,
                alocacoes_ane, equipas_set
            )
            if pode:
                # Calcular custo: afinidade com todos os cirs do macro
                pcts = [
                    afinidade(ane, cir, t, afinidades)
                    for cir in macro["cirs"]
                    for t in macro["tSlots"]
                ]
                pct_media = sum(pcts) / max(len(pcts), 1)

                # Bónus de continuidade: se já alocado no mesmo cirurgião/dia
                bonus = 0
                for b in macro["micro"]:
                    for ja in alocacoes_ane.get(ane, []):
                        if ja["cir"] == b["cir"] and ja["dia"] == b["dia"]:
                            bonus = 20; break

                custo = max(0, 100 - pct_media - bonus)
                candidatos.append((custo, ane, pct_media))

        if candidatos:
            # Escolher melhor candidato
            candidatos.sort()
            _, melhor_ane, pct = candidatos[0]

            # Verificar fixações (forçar ane específico)
            for r in restricoes:
                if r["tipo"] == "fixar" and r.get("slot") in macro["tSlots"]:
                    if r["ane"] in [c[1] for c in candidatos]:
                        melhor_ane = r["ane"]
                        pct = afinidade(melhor_ane, macro["cirs"][0],
                                        macro["tSlots"][0], afinidades)
                        break

            slots_str = "+".join(TURNO_L[t] for t in macro["tSlots"])
            razao = f"afinidade {pct:.0f}% {slots_str}" if pct > 0 else f"disponível {slots_str}"

            for b in macro["micro"]:
                resultado_map[b["id"]] = melhor_ane
                razao_map[b["id"]] = razao
                alocacoes_ane[melhor_ane].append(b)
            continue

        # --- Fallback: tentar por turno separado ---
        # Agrupar micro por tIdx
        por_turno: dict[int, list] = defaultdict(list)
        for b in macro["micro"]:
            for t in b.get("tSlots", [b["tIdx"]]):
                por_turno[t].append(b)

        ane_por_turno: dict[int, str] = {}
        # Preferir continuidade: se turno manhã já tem ane, tentar o mesmo à tarde
        for t in sorted(por_turno.keys()):
            micro_t = por_turno[t]
            # Macro parcial só para este turno
            macro_t = {**macro, "tSlots": [t], "micro": micro_t}

            # Preferir ane já alocado em turno anterior do mesmo macro
            preferido = list(ane_por_turno.values())[-1] if ane_por_turno else None
            if preferido:
                pode, _ = ane_cobre_macro(
                    preferido, macro_t, disponibilidades, restricoes_ane,
                    alocacoes_ane, equipas_set
                )
                if pode:
                    for b in micro_t:
                        if b["id"] not in resultado_map:
                            resultado_map[b["id"]] = preferido
                            pct = afinidade(preferido, b["cir"], t, afinidades)
                            razao_map[b["id"]] = f"continuidade {TURNO_L[t]} {pct:.0f}%"
                            alocacoes_ane[preferido].append(b)
                    ane_por_turno[t] = preferido
                    continue

            # Sem preferido disponível — Hungarian para este turno
            cands_t = []
            for ane in anestesistas:
                if ane == preferido: continue  # já tentámos
                pode, _ = ane_cobre_macro(
                    ane, macro_t, disponibilidades, restricoes_ane,
                    alocacoes_ane, equipas_set
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
                        razao_map[b["id"]] = f"afinidade {pct:.0f}% {TURNO_L[t]}"
                        alocacoes_ane[melhor].append(b)
                ane_por_turno[t] = melhor
            else:
                for b in micro_t:
                    if b["id"] not in resultado_map:
                        resultado_map[b["id"]] = None
                        razao_map[b["id"]] = f"sem candidato {TURNO_L[t]}"

    # --- Construir resultado final ---
    resultado = []
    for b in blocos:
        ane   = resultado_map.get(b["id"])
        razao = razao_map.get(b["id"], "não processado")
        resultado.append({"id": b["id"], "ane": ane, "razao": razao})

    return resultado
