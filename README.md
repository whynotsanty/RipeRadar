# RipeRadar: Sistema de Monitorização Inteligente da Maturação de Frutas

## 📋 Visão Geral

**RipeRadar** é um sistema de IoT integrado para monitorização em tempo real da maturação de frutas, combinando sensores biométricos de baixa potência (BLE) com visão computacional. Este projeto académico demonstra a aplicação de Machine Learning em cenários edge computing, avaliando o impacto de diferentes arquiteturas de processamento no consumo energético de dispositivos.

### Objetivo Principal

Desenvolver uma solução para classificação automática do estado de maturação de frutas utilizando:
- **Sensores ambientais** (temperatura, humidade, pressão, VOC)
- **Visão computacional** (classificação visual da fruta)
- **Comunicação BLE + MQTT** para transmissão de dados
- **Análise comparativa** de pipelines de processamento

---

## Arquitetura do Sistema

### Componentes de Hardware

| Componente | Modelo | Função |
|-----------|--------|--------|
| **Sensor Principal** | NICLA Sense ME | Coleta ambiental (T, H, P, VOC) via BLE |
| **Câmara/Visão** | Arduino Nano 33 | Captura e classificação visual |
| **Gateway** | Raspberry Pi | Bridge BLE-MQTT, orquestração |
| **Broker MQTT** | HiveMQ Cloud | Comunicação remota, armazenamento |

### Fluxo de Dados

```
[NICLA Sense ME] ─BLE─> [Gateway PC/RPi] ─MQTT─> [HiveMQ Cloud]
[Arduino + Câmara] ─┘                               ↓
                                              [Backend/Análise]
```

### Cenários Experimentais Avaliados

1. **Repouso (Idle)**: Baseline de consumo energético
2. **Inferência Local**: Processamento sem envio MQTT
3. **Pipeline Completa**: Coleta, processamento e transmissão MQTT

---

## Estrutura do Projeto

```
RipeRadar/
├── arduino-scripts/           # Código para dispositivos
│   ├── nano_ble33_sense_camera.ino
│   ├── nicla_sense_me.ino
│   └── UNOr4Wifi.ino
├── scripts/                   # Python - orquestração e análise
│   ├── gateway_mqtt.py       # Gateway BLE-MQTT
│   └── config.yaml           # Configuração centralizada
├── data/                      # Dados experimentais
│   ├── raw/                  # Dados brutos capturados
│   │   ├── idle.csv
│   │   ├── sem_mqtt.csv
│   │   └── com_mqtt.csv
├── env/                       # Ambiente de execução
│   ├── requirements.txt
└── LICENSE
```

---

## Instalação e Configuração

### Pré-requisitos

- Python 3.8+
- Broker MQTT (HiveMQ Cloud ou local)
- Dispositivos Arduino/NICLA Sense ME
- Bibliotecas BLE e MQTT

---

##  Utilização

### 1. Gateway MQTT
```bash
python scripts/gateway_mqtt.py
```
- Liga-se aos sensores BLE
- Transmite dados para broker MQTT


### 4. Análise de Consumo Energético
```bash
python scripts/analisar_consumo.py
```
- Comparação entre os três cenários
- Gráficos de consumo (idle, sem MQTT, com MQTT)
- Estatísticas de desempenho

---

## Dados e Resultados

### Ficheiros de Dados Disponíveis

| Ficheiro | Descrição | Registos |
|----------|-----------|----------|
| `data/raw/idle.csv` | Baseline sem processamento | ~1000 |
| `data/raw/sem_mqtt.csv` | Inferência local | ~1000 |
| `data/raw/com_mqtt.csv` | Pipeline MQTT completa | ~1000 |

### Métricas Avaliadas

- **Consumo de energia**: mW, mAh, duração de bateria
- **Latência**: Tempo de captura → transmissão
- **Precisão**: Classificação de maturação
- **Disponibilidade**: Taxa de uptime/conexão

---

## Tecnologias Utilizadas

### Software & Bibliotecas
- **Python 3.8+**
  - `bleak` - BLE client
  - `paho-mqtt` - Cliente MQTT
  - `pandas`, `numpy` - Análise de dados
  - `scikit-learn` - ML/classificação
  - `matplotlib`, `seaborn` - Visualização

- **Infraestrutura**
  - HiveMQ Cloud (broker MQTT)
  - Docker (containerização)
  - Conda/pip (gestão de dependências)


## Visualizações Disponíveis

Análise em `data/raw/`:

### `gerar_boxplot.py`
Cria boxplots de consumo por cenário
```
Cenário              | Min   | Q1    | Mediana | Q3    | Max
Repouso (Idle)      | 85mW  | 95mW  | 100mW   | 105mW | 115mW
Inferência (Sem)    | 200mW | 220mW | 240mW   | 260mW | 280mW
Pipeline (Com)      | 320mW | 350mW | 380mW   | 410mW | 450mW
```

### `gerar_energia_acumulada.py`
Visualiza energia acumulada ao longo do tempo

### `gerar_perfil_temporal.py`
Análise temporal de padrões de consumo

---

## Autores e Contribuições

**Autores**: Eduarda Pereira, Gonçalo Ferreira, Gonçalo Magalhães  
**Instituição**: Universidade do Minho  
**Ano Letivo**: 2025-2026
**UC**: Internet das Coisas Aplicada
---

## Licença

Este projeto está licenciado sob a **Licença MIT**. Veja [LICENSE](LICENSE) para detalhes.

---

## Referências e Recursos

### Documentação Oficial
- [NICLA Sense ME Datasheet](https://docs.arduino.cc/hardware/nicla-sense-me)
- [Bleak - BLE Client](https://bleak.readthedocs.io/)
- [Eclipse Paho MQTT](https://www.eclipse.org/paho/)
- [HiveMQ Cloud](https://www.hivemq.com/mqtt-cloud/)

### Papers Relacionados
- IoT em monitorização agrícola
- Edge computing e consumo energético
- Classificação de frutas com visão computacional
