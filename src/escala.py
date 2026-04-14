"""Entry point — lê payload.json, chama alocar(), escreve resultado.json."""

import json
import argparse
import sys
import os
from hungarian import alocar


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    parser.add_argument("--output",  required=True)
    args = parser.parse_args()

    with open(args.payload, encoding="utf-8") as f:
        payload = json.load(f)

    blocos                 = payload.get("blocos", [])
    disponibilidades_horas = payload.get("disponibilidades_horas", {})
    afinidades             = payload.get("afinidades", {})
    equipas                = payload.get("equipas", [])
    restricoes             = payload.get("restricoes", [])

    if not blocos:
        print("ERRO: nenhum bloco no payload", file=sys.stderr); sys.exit(1)
    if not disponibilidades_horas:
        print("ERRO: disponibilidades_horas vazio", file=sys.stderr); sys.exit(1)

    print(f"Payload: {len(blocos)} blocos | {len(disponibilidades_horas)} anestesistas")

    resultado = alocar(
        blocos=blocos,
        disponibilidades_horas=disponibilidades_horas,
        afinidades=afinidades,
        equipas=equipas,
        restricoes=restricoes,
    )

    alocados = sum(1 for r in resultado if r.get("ane"))
    sem      = len(resultado) - alocados

    output_obj = {
        "alocacoes": resultado,
        "stats": {"total": len(resultado), "alocados": alocados, "sem_cobertura": sem},
        "avisos": [r["razao"] for r in resultado if not r.get("ane") and r.get("razao")][:20],
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_obj, f, ensure_ascii=False, indent=2)

    print(f"Resultado: {alocados}/{len(resultado)} alocados → {args.output}")


if __name__ == "__main__":
    main()
