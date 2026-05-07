import random
import asyncio
import re
import os
import json
import ssl
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from bleak import BleakClient, BleakScanner

# --- TEST STAGE CONFIGURATION ---
# Stage A (Base Idle):  ENABLE_BLE = False | ENABLE_MQTT = False
# Stage B (Local Edge): ENABLE_BLE = True  | ENABLE_MQTT = False
# Stage C (Full Cycle): ENABLE_BLE = True  | ENABLE_MQTT = True

ENABLE_BLE = True
ENABLE_MQTT = False

# 1. Carregamento de credenciais MQTT
load_dotenv()
MQTT_BROKER = "04f11400208444d287dcce716d5d4823.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = os.getenv("MQTT_USER") 
MQTT_PASS = os.getenv("MQTT_PASS") 
MQTT_TOPIC = "riperadar/telemetria"
# Gera um ID único adicionando um número aleatório entre 1000 e 9999
random_id = f"RaspberryPi_Gateway_{random.randint(1000, 9999)}"

# 2. Configuração do Cliente MQTT 
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="random_id", protocol=mqtt.MQTTv5)

mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[MQTT] Ligado com sucesso ao HiveMQ Cloud!")
    else:
        print(f"[MQTT] Falha na ligação. Código de erro: {reason_code}")

mqtt_client.on_connect = on_connect

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    print(f"[MQTT] A ligação caiu! Motivo/Erro: {reason_code}")

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
if ENABLE_MQTT:
    print("[SYSTEM] Iniciando ligação MQTT...")
    mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start() # Inicia a thread de rede do MQTT em pano de fundo
else:
    print("[TEST] Stage B/A: MQTT desativado para teste de consumo.")

# Semáforo para evitar colisões no adaptador Bluetooth
ble_scan_lock = asyncio.Lock()

# Memória de Estado Global (Late Fusion Buffer)
system_state = {
    "temp": 0.0, 
    "hum": 0.0, 
    "hPa": 0.0, 
    "voc_gas": 0.0,
    "classe_dominante": "Desconhecido", 
    "confianca": 0.0
}

def enviar_telemetria():
    """Publica o pacote de dados fundidos no formato JSON via MQTT."""
    if not ENABLE_MQTT:
        return # <-- Aborta aqui no Stage B

    payload = json.dumps(system_state)
    try:
        mqtt_client.publish(MQTT_TOPIC, payload, qos=1)
    except Exception as e:
        print(f"[ERROR] Falha na publicação MQTT: {e}")


def nicla_handler(sender, data):
    """Processa pacotes BLE vindos do Nicla Sense ME (Gases)."""
    payload = data.decode('utf-8').strip()
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", payload)
    
    if len(nums) >= 4:
        system_state["temp"] = float(nums[0])
        system_state["hum"] = float(nums[1])
        system_state["hPa"] = float(nums[2])
        system_state["voc_gas"] = float(nums[3])
        
        print(f"[SENSE] Temp: {system_state['temp']}C | Hum: {system_state['hum']}% | VOC: {system_state['voc_gas']} Ohm")
        enviar_telemetria()

def vision_handler(sender, data):
    """Processa pacotes BLE vindos do Arduino Nano 33 (Visao IA)."""
    payload = data.decode('utf-8').strip()
    try:
        vision_data = json.loads(payload)
        if "classe_dominante" in vision_data and "confianca" in vision_data:
            system_state["classe_dominante"] = vision_data["classe_dominante"]
            system_state["confianca"] = float(vision_data["confianca"])
            
            print(f"[VISION] Alvo: {system_state['classe_dominante']} | Certeza: {system_state['confianca']}")
            enviar_telemetria()
    except json.JSONDecodeError:
        print(f"[WARN] Payload JSON invalido recebido da Camara: {payload}")

async def gerir_conexao(nome_dispositivo, char_uuid, handler):
    """Tarefa assincrona para manter conexao BLE estavel."""
    disconnect_event = asyncio.Event()

    def handle_disconnect(_):
        disconnect_event.set()

    while True:
        try:
            async with ble_scan_lock:
                device = await BleakScanner.find_device_by_name(nome_dispositivo, timeout=10.0)
            
            if device:
                disconnect_event.clear()
                async with BleakClient(device, timeout=15.0, disconnected_callback=handle_disconnect) as client:
                    await client.start_notify(char_uuid, handler)
                    await disconnect_event.wait()
                        
        except Exception as e:
                print(f"[ERROR] Excecao Bluetooth em {nome_dispositivo}: {repr(e)}")
                
        await asyncio.sleep(1)


async def main():
    print("[SYSTEM] RipeRadar Multi-Sensor Gateway Iniciado.")
    
    if ENABLE_BLE:
        print("[SYSTEM] Orquestrador Assíncrono BLE ativado. Pressione Ctrl+C para abortar.\n")
        tarefa_nicla = asyncio.create_task(gerir_conexao("RipeRadar", "19B10001-E8F2-537E-4F6C-D104768A1214", nicla_handler))
        await asyncio.sleep(2) 
        tarefa_visao = asyncio.create_task(gerir_conexao("Arduino33", "19B10011-E8F2-537E-4F6C-D104768A1214", vision_handler))
        
        await asyncio.gather(tarefa_nicla, tarefa_visao)
    else:
        print("[TEST] Stage A: Loop ocioso. BLE e MQTT desativados.")
        while True:
            await asyncio.sleep(1) # Mantém o script vivo sem fazer nada

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SYSTEM] Encerramento forçado do Gateway.")
        if ENABLE_MQTT:
            mqtt_client.disconnect()
            mqtt_client.loop_stop()