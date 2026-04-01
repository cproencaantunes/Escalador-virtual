"""
Converte notas OBS (output do Gemini) em restrições estruturadas.

Tipos:
  fixar    — forçar ane num slot
  excluir  — impedir ane num slot
  so_manha — ane só disponível manhã
  so_tarde — ane só disponível tarde
  ate_hora — ane sai mais cedo (informativo)
"""

TURNO_L = ["Seg-M","Seg-T","Ter-M","Ter-T","Qua-M","Qua-T","Qui-M","Qui-T","Sex-M","Sex-T"]
TURNO_IDX = {t: i for i, t in enumerate(TURNO_L)}
TIPOS = {"fixar","excluir","so_manha","so_tarde","ate_hora"}


def validar(restricoes_raw: list, anes_validos: set) -> tuple[list, list]:
    ok, avisos = [], []
    for r in restricoes_raw:
        ane  = str(r.get("ane","")).strip().upper()
        tipo = str(r.get("tipo","")).strip().lower()
        razao= str(r.get("razao","")).strip()
        if ane not in anes_validos:
            avisos.append(f"Sigla desconhecida: {ane!r}"); continue
        if tipo not in TIPOS:
            avisos.append(f"Tipo desconhecido: {tipo!r} ({ane})"); continue
        slot = r.get("slot")
        if slot is not None:
            if isinstance(slot, str): slot = TURNO_IDX.get(slot)
            if slot is None or not (0 <= int(slot) <= 9):
                avisos.append(f"Slot inválido para {ane}/{tipo}"); continue
            slot = int(slot)
        entry = {"ane": ane, "tipo": tipo, "razao": razao}
        if slot is not None: entry["slot"] = slot
        if tipo == "ate_hora": entry["hora"] = r.get("hora","")
        ok.append(entry)
    return ok, avisos


def prompt_gemini(disponibilidades: dict) -> str | None:
    """Gera prompt para Gemini converter OBS → restrições JSON."""
    linhas = []
    for ane, info in disponibilidades.items():
        obs = (info.get("obs") or "").strip()
        if not obs: continue
        slots = [TURNO_L[i] for i, v in enumerate(info["slots"]) if v]
        linhas.append(f'{ane} (disp: {", ".join(slots) or "nenhum"}): "{obs}"')
    if not linhas:
        return None
    return (
        "Converte estas notas de disponibilidade em restrições JSON estruturadas.\n\n"
        "Notas:\n" + "\n".join(linhas) + "\n\n"
        "Formato de cada restrição:\n"
        '{"ane":"SIGLA","tipo":"TIPO","slot":"TURNO_OPCIONAL","razao":"breve"}\n\n'
        "Tipos:\n"
        '  "fixar"    — ane deve ser alocado neste slot\n'
        '  "excluir"  — ane não pode ser alocado neste slot\n'
        '  "so_manha" — ane só disponível manhãs (sem slot)\n'
        '  "so_tarde" — ane só disponível tardes (sem slot)\n'
        '  "ate_hora" — sai mais cedo, acrescenta "hora":"HH:MM"\n\n'
        "Turnos válidos: Seg-M Seg-T Ter-M Ter-T Qua-M Qua-T Qui-M Qui-T Sex-M Sex-T\n"
        "Responde APENAS com array JSON puro, sem markdown.\n"
        "Se uma nota não implica restrição clara, não incluas nada.\n"
        'Exemplo: [{"ane":"JN","tipo":"fixar","slot":"Seg-T","razao":"Gastro Seg tarde"}]'
    )
