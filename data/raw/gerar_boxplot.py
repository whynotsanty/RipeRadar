import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def load_data():
    # Carregar os ficheiros (ajusta os nomes se necessário)
    df_idle = pd.read_csv('idle.csv')
    df_sem_mqtt = pd.read_csv('sem_mqtt.csv')
    df_com_mqtt = pd.read_csv('com_mqtt.csv')
    
    # Adicionar uma coluna para identificar o cenário
    df_idle['Cenário'] = '1. Repouso (Idle)'
    df_sem_mqtt['Cenário'] = '2. Inferência (Sem MQTT)'
    df_com_mqtt['Cenário'] = '3. Pipeline Completa (Com MQTT)'
    
    # Juntar tudo num único DataFrame
    df_all = pd.concat([df_idle, df_sem_mqtt, df_com_mqtt])
    
    # Converter Watts para miliWatts (mW) para melhor leitura (opcional)
    df_all['Power (mW)'] = df_all['power_w'] * 1000
    return df_all

def main():
    df = load_data()
    
    # Configurar o estilo académico
    plt.figure(figsize=(10, 6))
    sns.set_theme(style="whitegrid")
    
    # Criar o Boxplot
    ax = sns.boxplot(x='Cenário', y='Power (mW)', data=df, palette="Set2", showfliers=True)
    
    plt.title('Distribuição do Consumo Energético por Cenário', fontsize=14, pad=15)
    plt.ylabel('Potência (mW)', fontsize=12)
    plt.xlabel('Cenário de Execução', fontsize=12)
    
    # Guardar com alta resolução para o PDF do artigo
    plt.tight_layout()
    plt.savefig('grafico_boxplot_consumo.png', dpi=300)
    plt.show()

if __name__ == "__main__":
    main()