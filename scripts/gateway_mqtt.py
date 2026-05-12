import random
import asyncio
import re
import os
import json
import ssl
import time
import logging
import logging.handlers
import yaml
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from bleak import BleakClient, BleakScanner

# 1. Carregamento de configuração
load_dotenv()
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    CONFIG = yaml.safe_load(f)

# Configurar logging
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("")
logger.setLevel(getattr(logging, CONFIG['logging']['level']))
file_handler = logging.handlers.RotatingFileHandler(
    CONFIG['logging']['file'], maxBytes=CONFIG['logging']['max_bytes'], backupCount=CONFIG['logging']['backup_count']
)
file_handler.setFormatter(logging.Formatter(CONFIG['logging']['format']))
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(CONFIG['logging']['format']))
logger.addHandler(console_handler)

# Configurações MQTT
MQTT_BROKER = CONFIG['mqtt']['broker']
MQTT_PORT = CONFIG['mqtt']['port']
MQTT_TOPIC = CONFIG['mqtt']['topics']['telemetry']
HEALTHCHECK_TOPIC = CONFIG['mqtt']['topics']['healthcheck']
MQTT_USER = os.getenv("MQTT_USER") 
MQTT_PASS = os.getenv("MQTT_PASS")
random_id = f"RaspberryPi_Gateway_{random.randint(1000, 9999)}"

# 2. Configuração do Cliente MQTT 
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=random_id, protocol=mqtt.MQTTv5)
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0: logger.info("Ligado ao HiveMQ Cloud!")
    else: logger.error(f"Falha na ligação: {reason_code}")

mqtt_client.on_connect = on_connect
mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start() 

# Semáforo para o Bluetooth (necessário para não crashar o rádio do Pi)
ble_scan_lock = asyncio.Lock()

# Estado Global (apenas para cache interna, sem locks)
system_state = {
    "temp": 0.0, "hum": 0.0, "hPa": 0.0, "voc_gas": 0.0,
    "classe_dominante": "Desconhecido", "confianca": 0.0
}

def validar_valor(valor, key):
    ranges = {
        "temp": (CONFIG['validation']['temperature']['min'], CONFIG['validation']['temperature']['max']),
        "hum": (CONFIG['validation']['humidity']['min'], CONFIG['validation']['humidity']['max']),
        "hPa": (CONFIG['validation']['pressure']['min'], CONFIG['validation']['pressure']['max'])
    }
    if key in ranges:
        min_v, max_v = ranges[key]
        return min_v <= valor <= max_v
    return True

def aplicar_late_fusion(payload):
    """
    Calcula o estado através dos gases e aplica o Override se a visão falhar.
    """
    classe_visual = payload.get("classe_dominante", "desconhecido")
    confianca = float(payload.get("confianca", 100.0)) 
    voc_gas = float(payload.get("voc_gas", 0.0))

    fruto = classe_visual.split("_")[0].lower()
    if fruto not in ["banana", "maca", "laranja"]:
        fruto = "desconhecido"

    # 1. O Nicla calcula sempre a sua previsão com base nos Ohms (Ω)
    previsao_nicla = "desconhecido"
    if fruto in ["banana", "maca"]:
        if voc_gas > 17000:
            previsao_nicla = "fresca"
        elif 13000 <= voc_gas <= 17000:
            previsao_nicla = "madura"
        else:
            previsao_nicla = "podre"
    elif fruto == "laranja":
        if voc_gas >= 16000:
            previsao_nicla = "fresca"
        else:
            previsao_nicla = "podre"

    # 2. Avalia quem tem razão (Confiança < 60% = Nicla ganha)
    if confianca < 60.0 and fruto != "desconhecido":
        decisao_final = f"{fruto}_{previsao_nicla}"
    else:
        decisao_final = classe_visual

    # 3. Empacota os dados para enviar para o MQTT e para imprimir
    payload["classe_dominante"] = decisao_final
    payload["label_camara"] = classe_visual
    payload["previsao_nicla"] = previsao_nicla

    return payload


def publicar_dados(origem):
    """Publica e imprime o resumo da fusão."""
    try:
        payload_bruto = system_state.copy()
        payload_bruto["timestamp"] = time.time()
        payload_bruto["origem_trigger"] = origem

        # Aplica a inteligência da Fusão
        payload_final = aplicar_late_fusion(payload_bruto)

        # Envia para a Cloud
        mqtt_client.publish(MQTT_TOPIC, json.dumps(payload_final), qos=1)
        
        # O Print focado e direto que pediste
        logger.info(
            f"Decisão Final: {payload_final['classe_dominante']} | "
            f"Confiança Câmara: {payload_final['confianca']} | "
            f"Label Câmara: {payload_final['label_camara']} | "
            f"VOCs: {payload_final['voc_gas']} Ω | "
            f"Previsão Nicla: {payload_final['previsao_nicla']}"
        )
    except Exception as e:
        logger.error(f"Erro ao publicar: {e}")

def nicla_handler(sender, data):
    """Handler Nicla: Atualiza e publica imediatamente."""
    payload = data.decode('utf-8').strip()
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", payload)
    
    if len(nums) == 4:
        t, h, p, v = map(float, nums)
        if validar_valor(t, "temp") and validar_valor(h, "hum"):
            system_state.update({"temp": t, "hum": h, "hPa": p, "voc_gas": v})
            publicar_dados("nicla")
    else:
        logger.error(f"Payload Nicla inválido: {len(nums)} valores")

def vision_handler(sender, data):
    """Handler Visão: Atualiza e publica imediatamente."""
    try:
        vision_data = json.loads(data.decode('utf-8').strip())
        if "classe_dominante" in vision_data:
            system_state.update({
                "classe_dominante": vision_data["classe_dominante"],
                "confianca": float(vision_data.get("confianca", 0))
            })
            publicar_dados("vision")
    except Exception as e:
        logger.error(f"Erro JSON Câmara: {e}")

async def healthcheck_scheduler():
    while True:
        await asyncio.sleep(30)
        heartbeat = {"timestamp": time.time(), "status": "OK", "gateway_id": random_id}
        mqtt_client.publish(HEALTHCHECK_TOPIC, json.dumps(heartbeat), qos=1)

async def gerir_conexao(nome_dispositivo, char_uuid, handler, modo="notify"):
    char_uuid_lower = char_uuid.lower()
    while True:
        try:
            async with ble_scan_lock:
                device = await BleakScanner.find_device_by_name(nome_dispositivo, timeout=5.0)
            
            if device:
                async with BleakClient(device, timeout=10.0) as client:
                    if modo == "notify":
                        await client.start_notify(char_uuid_lower, handler)
                        while client.is_connected: await asyncio.sleep(1)
                    elif modo == "read":
                        data = await client.read_gatt_char(char_uuid_lower)
                        handler(None, data)
                        await client.disconnect()
        except Exception as e:
            logger.debug(f"[{nome_dispositivo}] BLE reconnecting... ({e})")
        await asyncio.sleep(2)

async def main():
    logger.info("Gateway em modo de Publicação")
    
    # Criar tarefas
    tarefa_nicla = asyncio.create_task(gerir_conexao(CONFIG['devices']['nicla']['name'], CONFIG['devices']['nicla']['uuid'], nicla_handler, "notify"))
    tarefa_visao = asyncio.create_task(gerir_conexao(CONFIG['devices']['arduino']['name'], CONFIG['devices']['arduino']['uuid'], vision_handler, "read"))
    tarefa_health = asyncio.create_task(healthcheck_scheduler())
    
    await asyncio.gather(tarefa_nicla, tarefa_visao, tarefa_health)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        mqtt_client.disconnect()
        mqtt_client.loop_stop()