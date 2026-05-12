import pandas as pd
import matplotlib.pyplot as plt

def main():
    df_idle = pd.read_csv('idle.csv')
    df_sem_mqtt = pd.read_csv('sem_mqtt.csv')
    df_com_mqtt = pd.read_csv('com_mqtt.csv')
    
    plt.figure(figsize=(10, 6))
    
    # Usar a coluna duration_sec (começa em 0) para normalizar o eixo do X
    plt.plot(df_idle['duration_sec'], df_idle['energy_ws'], label='Repouso (Idle)', color='green')
    plt.plot(df_sem_mqtt['duration_sec'], df_sem_mqtt['energy_ws'], label='Inferência (Sem MQTT)', color='orange')
    plt.plot(df_com_mqtt['duration_sec'], df_com_mqtt['energy_ws'], label='Completo (Com MQTT)', color='red')
    
    plt.title('Energia Acumulada (Joules) ao Longo do Tempo', fontsize=14)
    plt.ylabel('Energia Acumulada (Ws / Joules)', fontsize=12)
    plt.xlabel('Duração do Teste (Segundos)', fontsize=12)
    
    # Limitar o eixo X para o menor tempo de gravação dos 3 ficheiros para a comparação ser justa
    min_duration = min(df_idle['duration_sec'].max(), df_sem_mqtt['duration_sec'].max(), df_com_mqtt['duration_sec'].max())
    plt.xlim(0, min_duration)
    
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('grafico_energia_acumulada.png', dpi=300)
    plt.show()

if __name__ == "__main__":
    main()