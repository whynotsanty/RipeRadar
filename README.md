# RipeRadar: Intelligent Fruit Ripening Monitoring System

## 📋 Overview

**RipeRadar** is an integrated IoT system for real-time fruit ripening monitoring, combining low-power biometric sensors (BLE) with computer vision. This academic project demonstrates the application of Machine Learning in edge computing scenarios, evaluating the impact of different processing architectures on device energy consumption.

### Main Objective

Develop a solution for the automatic classification of the fruit ripening state using:
- **Environmental sensors** (temperature, humidity, pressure, VOC)
- **Computer vision** (visual fruit classification)
- **BLE + MQTT communication** for data transmission
- **Comparative analysis** of processing pipelines

---

## System Architecture

### Hardware Components

| Component | Model | Function |
|-----------|--------|--------|
| **Main Sensor** | NICLA Sense ME | Environmental data collection (T, H, P, VOC) via BLE |
| **Camera/Vision** | Arduino Nano 33 | Visual capture and classification |
| **Gateway** | Raspberry Pi | BLE-MQTT bridge, orchestration |
| **MQTT Broker** | HiveMQ Cloud | Remote communication, storage |

### Data Flow

```text
[NICLA Sense ME] ─BLE─> [Gateway PC/RPi] ─MQTT─> [HiveMQ Cloud]
[Arduino + Camera] ─┘                                  ↓
                                               [Backend/Analysis]
```

### Evaluated Experimental Scenarios

1. **Idle**: Energy consumption baseline
2. **Local Inference**: Processing without MQTT transmission
3. **Complete Pipeline**: Data collection, processing, and MQTT transmission

---

## Project Structure

```text
RipeRadar/
├── arduino-scripts/           # Code for devices
│   ├── nano_ble33_sense_camera.ino
│   ├── nicla_sense_me.ino
│   └── UNOr4Wifi.ino
├── scripts/                   # Python - orchestration and analysis
│   ├── gateway_mqtt.py        # BLE-MQTT Gateway
│   └── config.yaml            # Centralized configuration
├── data/                      # Experimental data
│   ├── raw/                   # Raw captured data
│   │   ├── idle.csv
│   │   ├── sem_mqtt.csv
│   │   └── com_mqtt.csv
├── env/                       # Execution environment
│   ├── requirements.txt
└── LICENSE
```

---

## Installation and Configuration

### Prerequisites

- Python 3.8+
- MQTT Broker (HiveMQ Cloud or local)
- Arduino/NICLA Sense ME devices
- BLE and MQTT libraries

---

## Usage

### 1. MQTT Gateway
```bash
python scripts/gateway_mqtt.py
```
- Connects to BLE sensors
- Transmits data to the MQTT broker

### 2. Energy Consumption Analysis
```bash
python scripts/analisar_consumo.py
```
- Comparison between the three scenarios
- Consumption graphs (idle, without MQTT, with MQTT)
- Performance statistics

---

## Data and Results

### Available Data Files

| File | Description | Records |
|----------|-----------|----------|
| `data/raw/idle.csv` | Baseline without processing | ~1000 |
| `data/raw/sem_mqtt.csv` | Local inference | ~1000 |
| `data/raw/com_mqtt.csv` | Complete MQTT pipeline | ~1000 |

### Evaluated Metrics

- **Energy consumption**: mW, mAh, battery life
- **Latency**: Capture time → transmission
- **Accuracy**: Ripening classification
- **Availability**: Uptime/connection rate

---

## Technologies Used

### Software & Libraries
- **Python 3.8+**
  - `bleak` - BLE client
  - `paho-mqtt` - MQTT Client
  - `pandas`, `numpy` - Data analysis
  - `scikit-learn` - ML/classification
  - `matplotlib`, `seaborn` - Visualization

- **Infrastructure**
  - HiveMQ Cloud (MQTT broker)
  - Docker (containerization)
  - Conda/pip (dependency management)

## Available Visualizations

Analysis in `data/raw/`:

### `gerar_boxplot.py`
Creates consumption boxplots per scenario
```text
Scenario             | Min   | Q1    | Median  | Q3    | Max
Idle                 | 85mW  | 95mW  | 100mW   | 105mW | 115mW
Inference (Without)  | 200mW | 220mW | 240mW   | 260mW | 280mW
Pipeline (With)      | 320mW | 350mW | 380mW   | 410mW | 450mW
```

### `gerar_energia_acumulada.py`
Visualizes accumulated energy over time

### `gerar_perfil_temporal.py`
Temporal analysis of consumption patterns

---

## Authors and Contributions

**Authors**: Eduarda Pereira, Gonçalo Ferreira, Gonçalo Magalhães  
**Institution**: University of Minho  
**Academic Year**: 2025-2026  
**Course**: Applied Internet of Things  

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

## References and Resources

### Official Documentation
- [NICLA Sense ME Datasheet](https://docs.arduino.cc/hardware/nicla-sense-me)
- [Bleak - BLE Client](https://bleak.readthedocs.io/)
- [Eclipse Paho MQTT](https://www.eclipse.org/paho/)
- [HiveMQ Cloud](https://www.hivemq.com/mqtt-cloud/)

### Related Papers
- IoT in agricultural monitoring
- Edge computing and energy consumption
- Fruit classification with computer vision
