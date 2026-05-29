import random
import asyncio
import re
import os
import json
import ssl
import time
import threading
import logging
import logging.handlers
import yaml
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from bleak import BleakClient, BleakScanner

# -----------------------------------------------------------------------------
# 1. CARREGAMENTO DE CONFIGURAÇÃO E LOGGING
# -----------------------------------------------------------------------------
load_dotenv()
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    CONFIG = yaml.safe_load(f)

# Configurar logging
os.makedirs("logs", exist_ok=True)
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
logger.info("Gateway Iniciado - Modo de Publicacao Temporizada (5s) + SSH Override")
logger.info("=" * 80)

# Configurações MQTT
MQTT_BROKER = CONFIG['mqtt']['broker']
MQTT_PORT = CONFIG['mqtt']['port']
MQTT_TOPIC = CONFIG['mqtt']['topics']['telemetry']
HEALTHCHECK_TOPIC = CONFIG['mqtt']['topics']['healthcheck']
MQTT_USER = os.getenv("MQTT_USER") 
MQTT_PASS = os.getenv("MQTT_PASS")
random_id = f"RaspberryPi_Gateway_{random.randint(1000, 9999)}"

# -----------------------------------------------------------------------------
# 2. CONFIGURAÇÃO DO CLIENTE MQTT
# -----------------------------------------------------------------------------
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=random_id, protocol=mqtt.MQTTv5)
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0: logger.info("Ligado ao HiveMQ Cloud!")
    else: logger.error(f"Falha na ligacao: {reason_code}")

mqtt_client.on_connect = on_connect
mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start() 

# Locks para paralelismo seguro
ble_scan_lock = asyncio.Lock()
state_lock = threading.Lock() 

# Estado Global (Memória partilhada)
system_state = {
    "temp": 0.0, "hum": 0.0, "hPa": 0.0, "voc_gas": 0.0,
    "classe_dominante": "Desconhecido", "confianca": 0.0
}

# -----------------------------------------------------------------------------
# LÓGICA CORE: VALIDAÇÃO E FUSÃO (LATE FUSION)
# -----------------------------------------------------------------------------
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

    # 1. O Nicla calcula a sua previsao com base nos limiares documentados
    previsao_nicla = "desconhecido"
    
    if fruto == "banana":
        if voc_gas < 27500:
            previsao_nicla = "fresca"
        elif 27500 <= voc_gas:
            previsao_nicla = "podre"
    
    elif fruto == "maca":
        if voc_gas < 33000:
            previsao_nicla = "fresca"
        elif 33000 <= voc_gas:
            previsao_nicla = "podre"
            
    elif fruto == "laranja":
        if voc_gas < 28500:
            previsao_nicla = "fresca"
        elif 28500 <= voc_gas:
            previsao_nicla = "podre"

    # 2. Avalia quem tem razão (Confiança < 60% = Nicla ganha)
    if confianca < 0.60 and fruto != "desconhecido":
        decisao_final = f"{fruto}_{previsao_nicla}"
    else:
        decisao_final = classe_visual

    # 3. Empacota os dados para enviar para o MQTT
    payload["classe_dominante"] = decisao_final
    payload["label_camara"] = classe_visual
    payload["previsao_nicla"] = previsao_nicla

    return payload

# -----------------------------------------------------------------------------
# CONTROLADOR DE TERMINAL VIA SSH (OVERRIDE MANUAL)
# -----------------------------------------------------------------------------
def forcar_classe(nova_classe):
    # Gera uma confiança aleatória entre 60% (0.60) e 100% (1.00)
    confianca_random = round(random.uniform(0.60, 1.00), 3)
    
    with state_lock:
        system_state["classe_dominante"] = nova_classe
        system_state["confianca"] = confianca_random
        
    logger.info(f"👉 [OVERRIDE APLICADO] Classe forçada: {nova_classe} | Confiança: {confianca_random}")

def loop_de_input_terminal():
    """Fica à espera de comandos escritos no terminal SSH em background"""
    time.sleep(2) # Pequena pausa apenas para as mensagens iniciais passarem
    logger.info("=" * 80)
    logger.info("👉 MODO TESTE ATIVO: Escreva no terminal e prima ENTER:")
    logger.info("   'bp' = Banana Podre | 'bf' = Banana Fresca")
    logger.info("   'lp' = Laranja Podre | 'lf' = Laranja Fresca")
    logger.info("   'mp' = Maca Podre   | 'mf' = Maca Fresca")
    logger.info("=" * 80)
    
    while True:
        try:
            comando = input().strip().lower() # Lê o que o utilizador escreve e carrega ENTER
            if comando == 'bp': forcar_classe("banana_podre")
            elif comando == 'bf': forcar_classe("banana_fresca")
            elif comando == 'lp': forcar_classe("laranja_podre")
            elif comando == 'lf': forcar_classe("laranja_fresca")
            elif comando == 'mp': forcar_classe("maca_podre")
            elif comando == 'mf': forcar_classe("maca_fresca")
            else:
                if comando != "": logger.warning(f"Comando desconhecido: '{comando}'. Use apenas bp, bf, lp, lf, mp ou mf.")
        except Exception:
            pass # Ignora erros de input ao fechar o programa

def iniciar_escuta_terminal():
    """Inicia a thread do terminal"""
    thread_input = threading.Thread(target=loop_de_input_terminal, daemon=True)
    thread_input.start()

# -----------------------------------------------------------------------------
# HANDLERS BLE (Atualizam a memória silenciosamente)
# -----------------------------------------------------------------------------
def nicla_handler(sender, data):
    payload = data.decode('utf-8').strip()
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", payload)
    
    if len(nums) == 4:
        t, h, p, v = map(float, nums)
        if p > 10000: p = p / 100.0 # Converte Pa para hPa
        
        if validar_valor(t, "temp") and validar_valor(h, "hum"):
            with state_lock:
                system_state.update({"temp": t, "hum": h, "hPa": p, "voc_gas": v})
    else:
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
    except Exception as e:
        logger.error(f"Erro JSON Camara: {e}")

# -----------------------------------------------------------------------------
# SCHEDULERS (Tratam da Publicação MQTT)
# -----------------------------------------------------------------------------
async def publicacao_periodica_scheduler():
    """
    O Relógio Mestre: A cada 5 segundos exatos publica.
    """
    logger.info("Scheduler de Publicacao ativado (Intervalo: 5s)")
    while True:
        await asyncio.sleep(5)  
        try:
            with state_lock:
                payload_bruto = system_state.copy()
            
            payload_bruto["timestamp"] = time.time()
            payload_bruto["origem_trigger"] = "timer_5s"

            # Aplica a inteligência da Fusão
            payload_final = aplicar_late_fusion(payload_bruto)

            # Envia para a Cloud
            mqtt_client.publish(MQTT_TOPIC, json.dumps(payload_final), qos=1)
            
            logger.info(
                f"[PUB 5s] Fusao Final: {payload_final['classe_dominante']} | "
                f"Camara: {payload_final['label_camara']} ({payload_final['confianca']:.2f}) | "
                f"Gases: {payload_final['voc_gas']} Ohms | Nicla diz: {payload_final['previsao_nicla']}"
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
async def gerir_conexao(nome_dispositivo, char_uuid, handler, modo="notify"):
    char_uuid_lower = char_uuid.lower()
    while True:
        try:
            async with ble_scan_lock:
                device = await BleakScanner.find_device_by_name(nome_dispositivo, timeout=3.0)
            
            if device:
                async with BleakClient(device, timeout=10.0) as client:
                    if modo == "notify":
                        await client.start_notify(char_uuid_lower, handler)
                        while client.is_connected: 
                            await asyncio.sleep(1)
                    elif modo == "read":
                        data = await client.read_gatt_char(char_uuid_lower)
                        handler(None, data)
                        await client.disconnect() 
        except Exception as e:
            if "was disconnected" not in str(e) and "not found" not in str(e):
                pass
        
        await asyncio.sleep(1)

# -----------------------------------------------------------------------------
# ARRANQUE PRINCIPAL
# -----------------------------------------------------------------------------
async def main():
    logger.info("Iniciando conectores BLE em pano de fundo...")
    
    # Ativar a escuta de terminal para SSH
    iniciar_escuta_terminal()
    
    tarefa_nicla = asyncio.create_task(
        gerir_conexao(CONFIG['devices']['nicla']['name'], CONFIG['devices']['nicla']['uuid'], nicla_handler, "notify")
    )
    
    UUID_CHAR_ARDUINO = "19B10011-E8F2-537E-4F6C-D104768A1214"
    tarefa_visao = asyncio.create_task(
        gerir_conexao(CONFIG['devices']['arduino']['name'], UUID_CHAR_ARDUINO, vision_handler, "notify")
    )
    
    tarefa_pub = asyncio.create_task(publicacao_periodica_scheduler())
    tarefa_health = asyncio.create_task(healthcheck_scheduler())
    
    await asyncio.gather(tarefa_nicla, tarefa_visao, tarefa_pub, tarefa_health)
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Encerrando Gateway...")
        mqtt_client.disconnect()
        mqtt_client.loop_stop()
