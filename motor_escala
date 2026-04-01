import pandas as pd
import json

def processar_motor_escala(dados_json):
    # Converte o JSON recebido do AppScript para DataFrame
    df = pd.DataFrame(dados_json)
    
    # 1. TRATAMENTO DE CÉLULAS MESCLADAS (DATA)
    # O AppScript envia a data apenas na primeira das 33 linhas.
    df['Data'] = df['Data'].ffill()
    
    propostas = []

    # 2. LÓGICA POR SALA (Exemplo Sala 1 - Colunas G e H no Operacional)
    # Esta lógica repete-se para as 10 salas e para os gabinetes TJEE
    salas = ['Sala 1', 'Sala 2', 'Sala 3', 'Sala 4', 'Sala 5', 
             'Sala 6', 'Sala 7', 'Sala 8', 'Sala 9', 'Sala 10', 'TJEE']

    for sala in salas:
        # Identifica blocos MICRO (Doente via HCIS)
        # O identificador de mudança é um novo HCIS ou um novo Cirurgião
        df[f'Grupo_{sala}'] = (
            (df[f'HCIS_{sala}'] != df[f'HCIS_{sala}'].shift()) | 
            (df[f'Cirurgiao_{sala}'] != df[f'Cirurgiao_{sala}'].shift())
        ).cumsum()

        # Agrupa para criar a proposta
        blocos = df.groupby([f'Grupo_{sala}', 'Data', f'Cirurgiao_{sala}']).agg(
            Hora_Inicio=('Hora', 'first'),
            Hora_Fim=('Hora', 'last'),
            HCIS=(f'HCIS_{sala}', 'first')
        ).reset_index()

        for _, bloco in blocos.iterrows():
            if pd.notna(bloco[f'Cirurgiao_{sala}']) and bloco[f'Cirurgiao_{sala}'] != "":
                propostas.append({
                    "data": bloco['Data'],
                    "hora": bloco['Hora_Inicio'],
                    "fim": bloco['Hora_Fim'],
                    "sala": sala,
                    "medico": bloco[f'Cirurgiao_{sala}'],
                    "hcis": bloco['HCIS'],
                    "sugestao_anestesista": "AGUARDAR_ALOCACAO" # Onde o seu algoritmo de IA/Regras entrará
                })

    return propostas

# Simulação de entrada via GitHub Actions
if __name__ == "__main__":
    # O GitHub Actions lerá o payload e chamará a função
    pass
