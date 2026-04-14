"""
Alocação de anestesistas — algoritmo micro/macro com disponibilidades horárias.
"""

import numpy as np
from scipy.optimize import linear_sum_assignment
from collections import defaultdict

DIAS_STR  = ["Seg","Ter","Qua","Qui","Sex"]
TURNO_L   = ["Seg-M","Seg-T","Ter-M","Ter-T","Qua-M","Qua-T","Qui-M","Qui-T","Sex-M","Sex-T"]
INTERVALO_MIN = 30


def sobreposicao(a_ini, a_fim, b_ini, b_fim) -> bool:
    return a_ini < b_fim and b_ini < a_fim


def compativel_temporal(blocoA, blocoB, mesma_equipa) -> bool:
    # Blocos em dias diferentes nunca conflituam
    if blocoA.get("dia") != blocoB.get("dia"):
        return True

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


def afinidade(ane, cir, tIdx, afinidades) -> float:
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


def slots_bloco(iniMin, fimMin) -> set:
    """Slots de 30min cobertos pelo bloco."""
    return set(range((iniMin // 30) * 30, fimMin, 30))


def construir_macros(blocos, equipas) -> list:
    equipa_de = {}
    for i, par in enumerate(equipas):
        eq_id = f"EQ{i}"
        for cir in par[:2]:
            equipa_de[cir.upper()] = eq_id

    grupos = defaultdict(list)
    for b in blocos:
        cir_u = b["cir"].upper()
        eq_id = equipa_de.get(cir_u)
        sala  = b.get("salaId", b.get("sala", ""))
        chave = (eq_id or cir_u, b["dia"], sala)
        grupos[chave].append(b)

    macros = []
    for (eq_ou_cir, dia, sala), micro_list in grupos.items():
        t_slots = sorted(set(s for b in micro_list for s in b.get("tSlots", [b["tIdx"]])))
        cirs    = list({b["cir"] for b in micro_list})
        macros.append({
            "id"    : f"M_{eq_ou_cir}_{dia}_{sala}",
            "cirs"  : cirs,
            "eq_id" : eq_ou_cir if str(eq_ou_cir).startswith("EQ") else None,
            "dia"   : dia,
            "sala"  : sala,
            "micro" : micro_list,
            "tSlots": t_slots,
        })
    return macros


def ane_cobre_macro(ane, macro, disp_horas, restricoes_ane, alocacoes_ane, equipas_set):
    """
    Verifica disponibilidade horária + restrições + compatibilidade temporal.
    disp_horas: {sigla: {dia_str: [slots_minutos]}}
    """
    dia_str  = DIAS_STR[macro["dia"]]
    slots_ane = set(disp_horas.get(ane, {}).get(dia_str, []))

    # 1. Disponibilidade horária — cada micro deve estar coberto
    for b in macro["micro"]:
        slots_b = slots_bloco(b["iniMin"], b["fimMin"])
        if not slots_b:
            # bloco sem slots válidos (iniMin=fimMin ou dados inválidos) → ignorar
            continue
        if not slots_ane:
            return False, "sem disponibilidade"
        if not slots_b.issubset(slots_ane):
            falta = sorted(slots_b - slots_ane)
            h = falta[0] if falta else b["iniMin"]
            return False, f"indisponível {h//60:02d}:{h%60:02d}"

    # 2. Restrições
    for r in restricoes_ane.get(ane, []):
        tipo = r["tipo"]
        slot = r.get("slot")
        if tipo == "so_manha" and any(t % 2 == 1 for t in macro["tSlots"]):
            return False, "só manhã"
        if tipo == "so_tarde" and any(t % 2 == 0 for t in macro["tSlots"]):
            return False, "só tarde"
        if tipo == "excluir" and slot in macro["tSlots"]:
            return False, f"excluído {TURNO_L[slot] if slot < len(TURNO_L) else slot}"

    # 3. Compatibilidade temporal
    ja_alocados = alocacoes_ane.get(ane, [])
    for micro in macro["micro"]:
        for ja in ja_alocados:
            mesma_eq = frozenset([micro["cir"].upper(), ja["cir"].upper()]) in equipas_set
            if not compativel_temporal(micro, ja, mesma_eq):
                return False, f"conflito temporal com {ja['cir']}"

    return True, "ok"


def alocar(blocos, disponibilidades_horas, afinidades, equipas, restricoes) -> list:
    anestesistas = sorted(disponibilidades_horas.keys())

    restricoes_ane = defaultdict(list)
    for r in restricoes:
        restricoes_ane[r["ane"]].append(r)

    equipas_set = {frozenset([p[0].upper(), p[1].upper()]) for p in equipas}

    macros = construir_macros(blocos, equipas)
    print(f"  Macros: {len(macros)} | Micro: {len(blocos)} | Anestesistas: {len(anestesistas)}")
    # Diagnóstico: verificar slots dos primeiros blocos
    for b in blocos[:3]:
        s = slots_bloco(b["iniMin"], b["fimMin"])
        dia_str = DIAS_STR[b["dia"]]
        print(f"  Bloco {b['id']}: {b['cir']} {dia_str} {b['iniMin']//60:02d}:{b['iniMin']%60:02d}-{b['fimMin']//60:02d}:{b['fimMin']%60:02d} → {len(s)} slots")
        # Contar anestesistas disponíveis para este bloco
        n_disp = sum(1 for a in anestesistas if s and s.issubset(set(disponibilidades_horas.get(a,{}).get(dia_str,[]))))
        print(f"    → {n_disp} anestesistas disponíveis")

    alocacoes_ane = defaultdict(list)
    resultado_map = {}
    razao_map     = {}

    # Ordenar cronologicamente: dia → hora de início
    # (mais natural — preenche Seg manhã antes de Seg tarde, etc.)
    def macro_ini(m):
        times = [b["iniMin"] for b in m["micro"]]
        return (m["dia"], min(times) if times else 9999)
    macros_ord = sorted(macros, key=macro_ini)

    for macro in macros_ord:

        # --- Tentar 1 ane para o macro inteiro ---
        candidatos = []
        for ane in anestesistas:
            pode, _ = ane_cobre_macro(
                ane, macro, disponibilidades_horas,
                restricoes_ane, alocacoes_ane, equipas_set)
            if pode:
                pcts = [afinidade(ane, cir, t, afinidades)
                        for cir in macro["cirs"]
                        for t in macro["tSlots"]]
                pct_media = sum(pcts) / max(len(pcts), 1)
                # Bónus forte: mesmo cirurgião+dia já alocado
                ja_mesmo_cir_dia = any(
                    ja["cir"] == b["cir"] and ja["dia"] == b["dia"]
                    for b in macro["micro"]
                    for ja in alocacoes_ane.get(ane, [])
                )
                bonus = 60 if ja_mesmo_cir_dia else 0
                candidatos.append((max(0, 100 - pct_media - bonus), ane, pct_media))

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

        # --- Fallback: por turno ---
        por_turno = defaultdict(list)
        for b in macro["micro"]:
            for t in b.get("tSlots", [b["tIdx"]]):
                por_turno[t].append(b)

        ane_por_turno = {}
        for t in sorted(por_turno.keys()):
            micro_t  = por_turno[t]
            macro_t  = {**macro, "tSlots": [t], "micro": micro_t}
            preferido = list(ane_por_turno.values())[-1] if ane_por_turno else None

            if preferido:
                pode, _ = ane_cobre_macro(
                    preferido, macro_t, disponibilidades_horas,
                    restricoes_ane, alocacoes_ane, equipas_set)
                if pode:
                    for b in micro_t:
                        if b["id"] not in resultado_map:
                            pct = afinidade(preferido, b["cir"], t, afinidades)
                            resultado_map[b["id"]] = preferido
                            razao_map[b["id"]]     = f"continuidade {TURNO_L[t] if t < len(TURNO_L) else t} {pct:.0f}%"
                            alocacoes_ane[preferido].append(b)
                    ane_por_turno[t] = preferido
                    continue

            cands_t = []
            for ane in anestesistas:
                if ane == preferido: continue
                pode, _ = ane_cobre_macro(
                    ane, macro_t, disponibilidades_horas,
                    restricoes_ane, alocacoes_ane, equipas_set)
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
                        razao_map[b["id"]]     = f"afinidade {pct:.0f}% {TURNO_L[t] if t < len(TURNO_L) else t}"
                        alocacoes_ane[melhor].append(b)
                ane_por_turno[t] = melhor
            else:
                for b in micro_t:
                    if b["id"] not in resultado_map:
                        resultado_map[b["id"]] = None
                        razao_map[b["id"]]     = f"sem candidato {TURNO_L[t] if t < len(TURNO_L) else t}"

    # --- Pass de continuidade: unificar ane para mesmo cir+dia ---
    # Para cada cir+dia, ver qual ane foi mais usado e tentar reatribuir os outros
    cir_dia_anes = defaultdict(list)  # (cir,dia) → [ane alocado]
    for b in blocos:
        ane = resultado_map.get(b["id"])
        if ane:
            cir_dia_anes[(b["cir"], b["dia"])].append(ane)

    for (cir, dia), anes_lista in cir_dia_anes.items():
        from collections import Counter
        mais_comum = Counter(anes_lista).most_common(1)[0][0]
        # Tentar reatribuir blocos deste cir+dia para o ane mais comum
        blocos_cd = [b for b in blocos
                     if b["cir"] == cir and b["dia"] == dia
                     and resultado_map.get(b["id"]) != mais_comum]
        for b in blocos_cd:
            ane_actual = resultado_map.get(b["id"])
            # Verificar se mais_comum pode cobrir este bloco
            macro_single = {"dia": b["dia"], "tSlots": b.get("tSlots",[b["tIdx"]]),
                            "micro": [b], "cirs": [b["cir"]]}
            # Temporariamente remover este bloco das alocações do ane_actual
            if ane_actual:
                alocacoes_ane[ane_actual] = [x for x in alocacoes_ane[ane_actual]
                                              if x["id"] != b["id"]]
            pode, _ = ane_cobre_macro(mais_comum, macro_single, disponibilidades_horas,
                                       restricoes_ane, alocacoes_ane, equipas_set)
            if pode:
                resultado_map[b["id"]] = mais_comum
                razao_map[b["id"]] = "continuidade cir+dia"
                alocacoes_ane[mais_comum].append(b)
            else:
                # Reverter
                if ane_actual:
                    alocacoes_ane[ane_actual].append(b)

    # Diagnóstico: top razões de falha
    sem = [razao_map.get(b["id"],"?") for b in blocos if not resultado_map.get(b["id"])]
    if sem:
        from collections import Counter
        top = Counter(sem).most_common(5)
        print(f"  Top razões sem candidato ({len(sem)} blocos):")
        for razao, n in top:
            print(f"    {n}x: {razao}")

    return [{"id": b["id"],
             "ane": resultado_map.get(b["id"]),
             "razao": razao_map.get(b["id"], "não processado")}
            for b in blocos]
