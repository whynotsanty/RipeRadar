import random
import asyncio
import re
import os
import json
import ssl
import time
import threading
import threading
import logging
import logging.handlers
import yaml
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from bleak import BleakClient, BleakScanner
# CORREÇÃO: Importação explícita das classes necessárias do InfluxDB
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# 1. Carregamento de configuração
load_dotenv()
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    CONFIG = yaml.safe_load(f)

# Configurar logging
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("RipeRadar")
logger = logging.getLogger("RipeRadar")
logger.setLevel(getattr(logging, CONFIG['logging']['level']))
file_handler = logging.handlers.RotatingFileHandler(
    CONFIG['logging']['file'], maxBytes=CONFIG['logging']['max_bytes'], backupCount=CONFIG['logging']['backup_count']
)
file_handler.setFormatter(logging.Formatter(CONFIG['logging']['format']))
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(CONFIG['logging']['format']))
logger.addHandler(console_handler)

logger.info("=" * 80)
logger.info("Gateway Iniciado - Modo de Publicacao Temporizada (30s)")
logger.info("=" * 80)

logger.info("=" * 80)
logger.info("Gateway Iniciado - Modo de Publicacao Temporizada (30s)")
logger.info("=" * 80)

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

# Inicialização do cliente InfluxDB Cloud usando as variáveis do teu .env
influx_client = InfluxDBClient(
    url=os.getenv("INFLUX_URL"), 
    token=os.getenv("INFLUX_TOKEN"), 
    org=os.getenv("INFLUX_ORG")
)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0: 
        logger.info("Ligado ao HiveMQ Cloud!")
        # Subscreve o tópico de autenticação e o de rastreabilidade de caixas
        client.subscribe("riperadar/v1/management/auth/+/session")
        client.subscribe("riperadar/v1/sorting/rfid/+/box_id")
    else: 
        logger.error(f"Falha na ligacao: {reason_code}")

def on_message(client, userdata, message):
    try:
        topic = message.topic
        payload = json.loads(message.payload.decode("utf-8"))
        
        # 1. Processamento e Persistência do Login (RFID Operadores/Chefes)
        if "management/auth" in topic:
            uid = payload.get('operator_id')
            role = payload.get('role')
            status = payload.get('status')
            logger.info(f"Cartão RFID detetado no Gateway! ID: {uid}")
            
            point = Point("user_sessions") \
                .tag("operator_id", uid) \
                .field("role", role) \
                .field("status", status)

            write_api.write(bucket=INFLUX_BUCKET, record=point)
            logger.info("Sessão de login persistida no InfluxDB com sucesso.")
            
        # 2. Processamento e Persistência do Tracking de Caixas (RFID Caixas de Fruta)
        elif "sorting/rfid" in topic:
            box_id = payload.get('box_id')
            status = payload.get('status')
            origin = payload.get('origin')
            logger.info(f"Tag RFID de caixa detetada no Gateway! ID: {box_id}")
            
            point = Point("mqtt_consumer") \
                .tag("box_id", box_id) \
                .tag("origin", origin) \
                .field("status", status)
                
            write_api.write(bucket=INFLUX_BUCKET, record=point)
            logger.info("Registo de caixa de fruta persistido no InfluxDB com sucesso.")
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")

# Associar as funções de callback ao cliente
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message 

mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# Locks para paralelismo seguro
# Locks para paralelismo seguro
ble_scan_lock = asyncio.Lock()
state_lock = threading.Lock() 
state_lock = threading.Lock() 

# Estado Global (Memória partilhada)
# Estado Global (Memória partilhada)
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

    # 1. O Nicla calcula sempre a sua previsão com base nos Ohms
    # 1. O Nicla calcula sempre a sua previsão com base nos Ohms
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
    if confianca < 0.60 and fruto != "desconhecido": 
        decisao_final = f"{fruto}_{previsao_nicla}"
    else:
        decisao_final = classe_visual

    # 3. Empacota os dados para enviar para o MQTT
    # 3. Empacota os dados para enviar para o MQTT
    payload["classe_dominante"] = decisao_final
    payload["label_camara"] = classe_visual
    payload["previsao_nicla"] = previsao_nicla

    return payload

# -----------------------------------------------------------------------------
# HANDLERS (Apenas atualizam a memória silenciosamente)
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# HANDLERS (Apenas atualizam a memória silenciosamente)
# -----------------------------------------------------------------------------
def nicla_handler(sender, data):
    payload = data.decode('utf-8').strip()
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", payload)
    
    if len(nums) == 4:
        t, h, p, v = map(float, nums)
        if p > 10000: p = p / 100.0 # Converte Pa para hPa
        
        if p > 10000: p = p / 100.0 # Converte Pa para hPa
        
        if validar_valor(t, "temp") and validar_valor(h, "hum"):
            with state_lock:
                system_state.update({"temp": t, "hum": h, "hPa": p, "voc_gas": v})
            with state_lock:
                system_state.update({"temp": t, "hum": h, "hPa": p, "voc_gas": v})
    else:
        logger.error(f"Payload Nicla invalido: {len(nums)} valores")
        logger.error(f"Payload Nicla invalido: {len(nums)} valores")

def vision_handler(sender, data):
    try:
        vision_data = json.loads(data.decode('utf-8').strip())
        if "classe_dominante" in vision_data:
            with state_lock:
                system_state.update({
                    "classe_dominante": vision_data["classe_dominante"],
                    "confianca": float(vision_data.get("confianca", 0))
                })
            with state_lock:
                system_state.update({
                    "classe_dominante": vision_data["classe_dominante"],
                    "confianca": float(vision_data.get("confianca", 0))
                })
    except Exception as e:
        logger.error(f"Erro JSON Camara: {e}")

# -----------------------------------------------------------------------------
# SCHEDULERS (Tratam da Publicação MQTT)
# -----------------------------------------------------------------------------
async def publicacao_periodica_scheduler():
    """
    O Relógio Mestre: A cada 30 segundos exatos publica.
    """
    logger.info("Scheduler de Publicacao ativado (Intervalo: 30s)")
    while True:
        await asyncio.sleep(30)
        try:
            with state_lock:
                payload_bruto = system_state.copy()
            
            payload_bruto["timestamp"] = time.time()
            payload_bruto["origem_trigger"] = "timer_30s"

            # Aplica a inteligência da Fusão
            payload_final = aplicar_late_fusion(payload_bruto)

            # Envia para a Cloud
            mqtt_client.publish(MQTT_TOPIC, json.dumps(payload_final), qos=1)
            
            logger.info(
                f"[PUBLICACAO 30s] Decisao: {payload_final['classe_dominante']} | "
                f"Conf. Camara: {payload_final['confianca']:.3f} | "
                f"Label Camara: {payload_final['label_camara']} | "
                f"VOCs: {payload_final['voc_gas']} Ohms | "
                f"Nicla: {payload_final['previsao_nicla']}"
            )
        except Exception as e:
            logger.error(f"Erro ao publicar: {e}")

async def healthcheck_scheduler():
    while True:
        await asyncio.sleep(30)
        heartbeat = {"timestamp": time.time(), "status": "OK", "gateway_id": random_id}
        mqtt_client.publish(HEALTHCHECK_TOPIC, json.dumps(heartbeat), qos=1)

# -----------------------------------------------------------------------------
# GESTOR DE CONEXÃO BLE
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# GESTOR DE CONEXÃO BLE
# -----------------------------------------------------------------------------
async def gerir_conexao(nome_dispositivo, char_uuid, handler, modo="notify"):
    char_uuid_lower = char_uuid.lower()
    while True:
        try:
            async with ble_scan_lock:
                device = await BleakScanner.find_device_by_name(nome_dispositivo, timeout=3.0)
                device = await BleakScanner.find_device_by_name(nome_dispositivo, timeout=3.0)
            
            if device:
                async with BleakClient(device, timeout=10.0) as client:
                    if modo == "notify":
                        await client.start_notify(char_uuid_lower, handler)
                        while client.is_connected: 
                            await asyncio.sleep(1)
                        while client.is_connected: 
                            await asyncio.sleep(1)
                    elif modo == "read":
                        data = await client.read_gatt_char(char_uuid_lower)
                        handler(None, data)
                        await client.disconnect() 
                        await client.disconnect() 
        except Exception as e:
            if "was disconnected" not in str(e) and "not found" not in str(e):
                pass
        
        await asyncio.sleep(1)
            if "was disconnected" not in str(e) and "not found" not in str(e):
                pass
        
        await asyncio.sleep(1)

async def main():
    logger.info("Iniciando conectores BLE em pano de fundo...")
    logger.info("Iniciando conectores BLE em pano de fundo...")
    
    tarefa_nicla = asyncio.create_task(gerir_conexao(CONFIG['devices']['nicla']['name'], CONFIG['devices']['nicla']['uuid'], nicla_handler, "notify"))
    tarefa_visao = asyncio.create_task(gerir_conexao(CONFIG['devices']['arduino']['name'], CONFIG['devices']['arduino']['uuid'], vision_handler, "read"))
    tarefa_pub = asyncio.create_task(publicacao_periodica_scheduler())
    tarefa_pub = asyncio.create_task(publicacao_periodica_scheduler())
    tarefa_health = asyncio.create_task(healthcheck_scheduler())
    
    await asyncio.gather(tarefa_nicla, tarefa_visao, tarefa_pub, tarefa_health)
    await asyncio.gather(tarefa_nicla, tarefa_visao, tarefa_pub, tarefa_health)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Encerrando Gateway...")
        logger.info("Encerrando Gateway...")
        mqtt_client.disconnect()
        mqtt_client.loop_stop()
