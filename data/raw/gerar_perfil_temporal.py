import pandas as pd
import matplotlib.pyplot as plt
import datetime
import re

def parse_logs(log_file):
    """Extrai os timestamps reais (datetime) do ficheiro txt."""
    timestamps = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            # Procura o formato [YYYY-MM-DD HH:MM:SS,ms]
            match = re.search(r'\[(.*?)\]', line)
            if match:
                date_str = match.group(1)
                try:
                    # Converter string do log para objeto datetime
                    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S,%f')
                    timestamps.append(dt)
                except ValueError:
                    continue
    return timestamps

def main():
    # Carrega o CSV do cenário mais completo
    df = pd.read_csv('com_mqtt.csv')
    
    # Converter a coluna timestamp_iso para datetime
    df['datetime'] = pd.to_datetime(df['timestamp_iso'])
    
    # Extrair os momentos em que houve publicações/inferências
    eventos_logs = parse_logs('com_mqtt.txt')
    
    plt.figure(figsize=(14, 6))
    plt.plot(df['datetime'], df['power_w'], label='Consumo de Potência (W)', color='tab:blue', linewidth=1.5)
    
    # Adicionar uma linha vertical por cada evento no log
    first_event = True
    for ev_time in eventos_logs:
        # Apenas para a legenda não ficar com 100 entradas repetidas
        label = 'Evento (Inferência/Publicação)' if first_event else ""
        plt.axvline(x=ev_time, color='red', linestyle='--', alpha=0.5, label=label)
        first_event = False

    plt.title('Perfil Energético Temporal com Eventos de Late Fusion (Com MQTT)', fontsize=14)
    plt.ylabel('Potência (W)', fontsize=12)
    plt.xlabel('Tempo', fontsize=12)
    plt.legend(loc='upper right')
    plt.grid(True, linestyle=':', alpha=0.7)
    
    plt.tight_layout()
    plt.savefig('grafico_perfil_temporal.png', dpi=300)
    plt.show()

if __name__ == "__main__":
    main()