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

# 1. Carregamento de credenciais MQTT
load_dotenv()

# Carregar configuração YAML
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    CONFIG = yaml.safe_load(f)

# Configurar logging em ficheiro
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("RipeRadar-Gateway")
logger.setLevel(getattr(logging, CONFIG['logging']['level']))

# Ficheiro com rotação
file_handler = logging.handlers.RotatingFileHandler(
    CONFIG['logging']['file'],
    maxBytes=CONFIG['logging']['max_bytes'],
    backupCount=CONFIG['logging']['backup_count']
)
file_handler.setFormatter(logging.Formatter(CONFIG['logging']['format']))
logger.addHandler(file_handler)

# Console também
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(CONFIG['logging']['format']))
logger.addHandler(console_handler)

logger.info("=" * 80)
logger.info("RipeRadar Multi-Sensor Gateway iniciado")
logger.info(f"Configuração carregada de: {config_path}")
logger.info("=" * 80)

# Configurações MQTT
MQTT_BROKER = CONFIG['mqtt']['broker']
MQTT_PORT = CONFIG['mqtt']['port']
MQTT_TOPIC = CONFIG['mqtt']['topics']['telemetry']
HEALTHCHECK_TOPIC = CONFIG['mqtt']['topics']['healthcheck']

# Credenciais (do .env para segurança)
MQTT_USER = os.getenv("MQTT_USER") 
MQTT_PASS = os.getenv("MQTT_PASS")
# Gera um ID único adicionando um número aleatório entre 1000 e 9999
random_id = f"RaspberryPi_Gateway_{random.randint(1000, 9999)}"

# 2. Configuração do Cliente MQTT 
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=random_id, protocol=mqtt.MQTTv5)

mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logger.info("Ligado com sucesso ao HiveMQ Cloud!")
    else:
        logger.error(f"Falha na ligação. Código de erro: {reason_code}")

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    logger.warning(f"Ligação MQTT caiu. Código: {reason_code}")

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start() # Inicia a thread de rede do MQTT em pano de fundo

# Semáforo para evitar colisões no adaptador Bluetooth
ble_scan_lock = asyncio.Lock()

# Lock para evitar race conditions no estado global
state_lock = threading.Lock()

# Flag para shutdown gracioso
shutdown_event = asyncio.Event()

# Configurações de validação (carregadas do YAML)
VALIDATION_CONFIG = {
    "temp_range": (CONFIG['validation']['temperature']['min'], CONFIG['validation']['temperature']['max']),
    "hum_range": (CONFIG['validation']['humidity']['min'], CONFIG['validation']['humidity']['max']),
    "hPa_range": (CONFIG['validation']['pressure']['min'], CONFIG['validation']['pressure']['max']),
    "staleness_timeout": CONFIG['fusion']['staleness_timeout_seconds'],
    "fusion_interval": CONFIG['fusion']['interval_seconds'],
    "required_data_age": CONFIG['fusion']['required_data_age_seconds']
}

# Métricas de fusão
fusion_metrics = {
    "total_published": 0,
    "last_fusion_time": None,
    "skipped_stale": 0
}

# Memória de Estado Global (Late Fusion Buffer)
system_state = {
    "temp": 0.0,
    "temp_timestamp": None,
    "hum": 0.0,
    "hum_timestamp": None,
    "hPa": 0.0,
    "hPa_timestamp": None,
    "voc_gas": 0.0,
    "voc_gas_timestamp": None,
    "classe_dominante": "Desconhecido",
    "confianca": 0.0,
    "vision_timestamp": None
}

def validar_valor(valor, key):
    """Valida se um valor está dentro da gama esperada.
    
    Args:
        valor (float): O valor a validar
        key (str): Chave do tipo de valor ('temp', 'hum', 'hPa')
    
    Returns:
        bool: True se válido, False caso contrário (com log de aviso)
    
    Raises:
        Nenhuma - erros são registados em log
    """
    if key == "temp":
        min_val, max_val = VALIDATION_CONFIG["temp_range"]
        if not (min_val <= valor <= max_val):
            logger.warning(f"Temperatura fora da gama: {valor}°C")
            return False
    elif key == "hum":
        min_val, max_val = VALIDATION_CONFIG["hum_range"]
        if not (min_val <= valor <= max_val):
            logger.warning(f"Humidade fora da gama: {valor}%")
            return False
    elif key == "hPa":
        min_val, max_val = VALIDATION_CONFIG["hPa_range"]
        if not (min_val <= valor <= max_val):
            logger.warning(f"Pressão fora da gama: {valor} hPa")
            return False
    return True

def verificar_staleness():
    """Verifica se algum sensor tem dados muito antigos."""
    agora = time.time()
    timeout = VALIDATION_CONFIG["staleness_timeout"]
    
    sensores_stale = []
    for sensor in ["temp_timestamp", "vision_timestamp"]:
        timestamp = system_state.get(sensor)
        if timestamp and (agora - timestamp) > timeout:
            sensores_stale.append(sensor.replace("_timestamp", ""))
    
    return sensores_stale

def pode_fazer_fusion():
    """Verifica se AMBOS os sensores têm dados recentes para fusão.
    
    Late fusion requer que ambos sensores tenham timestamps recentes.
    Se algum sensor está "stale" (dados antigos), a fusão é adiada.
    
    Returns:
        tuple: (bool, str) 
            - bool: True se pode fazer fusão, False caso contrário
            - str: Motivo detalhado para logging
    
    Examples:
        >>> pode_fazer, motivo = pode_fazer_fusion()
        >>> if pode_fazer:
        ...     publicar_fusao()
        ... else:
        ...     logger.debug(f"Fusion adiada: {motivo}")
    """
    agora = time.time()
    max_age = VALIDATION_CONFIG["required_data_age"]
    
    # Verificar se ambos sensores têm timestamps
    temp_ts = system_state.get("temp_timestamp")
    vision_ts = system_state.get("vision_timestamp")
    
    if not temp_ts or not vision_ts:
        return False, "Sensores ainda não têm dados"
    
    # Verificar se dados não são stale
    temp_age = agora - temp_ts
    vision_age = agora - vision_ts
    
    if temp_age > max_age:
        return False, f"Dados temp stale ({temp_age:.1f}s > {max_age}s)"
    if vision_age > max_age:
        return False, f"Dados vision stale ({vision_age:.1f}s > {max_age}s)"
    
    return True, f"Fusão OK (temp: {temp_age:.1f}s, vision: {vision_age:.1f}s)"

async def healthcheck_scheduler():
    """Publica heartbeat periódico para monitorização remota do gateway.
    
    A cada 30 segundos publica um "heartbeat" num topic especial que permite:
    - Detetar crashes imediatos (sem heartbeat = problema)
    - Monitorizar métricas (total fusions publicadas, stale events)
    - Verificar uptime do gateway
    - Trigger alertas no dashboard (ex: se sem heartbeat > 90s)
    
    Topic: riperadar/gateway/healthcheck
    Payload: JSON com timestamp, status, e métricas
    """
    logger.info("Scheduler de heartbeat iniciado")
    
    while True:
        await asyncio.sleep(30)  # A cada 30 segundos
        try:
            heartbeat_data = {
                "timestamp": time.time(),
                "gateway_id": random_id,
                "status": "OK",
                "uptime_seconds": time.time(),
                "metrics": {
                    "total_fusions_published": fusion_metrics["total_published"],
                    "skipped_stale_count": fusion_metrics["skipped_stale"],
                    "last_fusion_time": fusion_metrics["last_fusion_time"]
                }
            }
            mqtt_client.publish(HEALTHCHECK_TOPIC, json.dumps(heartbeat_data), qos=1)
            logger.debug(f"Heartbeat publicado: {fusion_metrics['total_published']} fusões")
        except Exception as e:
            logger.error(f"Falha ao publicar heartbeat: {e}")

async def fusion_scheduler():
    """Scheduler de Late Fusion - Publica dados fundidos a intervalos regulares.
    
    Este é o "coração" da late fusion. A cada N segundos:
    1. Verifica se AMBOS sensores têm dados recentes
    2. Se sim: Lê atomicamente o estado (com lock)
    3. Publica um pacote JSON com todas as métricas sincronizadas
    4. Se não: Aguarda e registar motivo
    
    Late Fusion vs Early Fusion:
    - Early: Publica sempre que chega um sensor (desincronizado)
    - Late: Publica apenas quando ambos estão prontos (sincronizado) ✓
    
    Intervalo configurável em config.yaml['fusion']['interval_seconds']
    """
    logger.info("Scheduler de late fusion iniciado")
    
    while True:
        await asyncio.sleep(VALIDATION_CONFIG["fusion_interval"])
        
        # Verificar se pode fazer fusão
        pode_fazer, motivo = pode_fazer_fusion()
        
        if pode_fazer:
            # Leitura atômica do estado (protegida por lock)
            with state_lock:
                # Cópia dos dados para publicar
                payload_dict = system_state.copy()
                payload_dict["fusion_timestamp"] = time.time()
                payload_dict["fusion_quality"] = "OK"
            
            # Publicar FORA do lock para não bloquear sensores
            try:
                payload = json.dumps(payload_dict)
                mqtt_client.publish(MQTT_TOPIC, payload, qos=1)
                fusion_metrics["total_published"] += 1
                fusion_metrics["last_fusion_time"] = time.time()
                logger.info(f"Fusão #{fusion_metrics['total_published']}: "
                           f"Temp={payload_dict['temp']:.1f}°C, "
                           f"Vision={payload_dict['classe_dominante']} ({payload_dict['confianca']:.0f}%)")
            except Exception as e:
                logger.error(f"Falha na publicação de fusão: {e}")
        else:
            # Log apenas a cada N iterações para não spamear
            if fusion_metrics["total_published"] % 5 == 0:
                logger.debug(f"Fusion aguardando: {motivo}")
                fusion_metrics["skipped_stale"] += 1

def nicla_handler(sender, data):
    """Processa pacotes BLE vindos do Nicla Sense ME (Sensor de Gases).
    
    O Nicla envia dados de temperatura, humidade, pressão e VOC (compostos
    voláteis) a cada ciclo de leitura. O handler faz:
    1. Parse do payload (4 floats separados por vírgula)
    2. Validação rigorosa (exactamente 4 valores)
    3. Range check (valores dentro de limites)
    4. Atualização thread-safe do estado global
    5. Trigger de fusão
    
    Args:
        sender: Referência do BLE characteristic
        data (bytes): Payload recebido (ex: "25.5,45.0,1013.2,5000.0")
    
    Raises:
        Nenhuma - erros são capturados e registados
    """
    payload = data.decode('utf-8').strip()
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", payload)
    
    # Validação rigorosa: exactamente 4 valores
    if len(nums) != 4:
        logger.error(f"Payload Nicla inválido: esperava 4 valores, recebeu {len(nums)} em '{payload}'")
        return
    
    temp_val = float(nums[0])
    hum_val = float(nums[1])
    hPa_val = float(nums[2])
    voc_val = float(nums[3])
    
    # Validar valores antes de atualizar
    if not (validar_valor(temp_val, "temp") and validar_valor(hum_val, "hum") and validar_valor(hPa_val, "hPa")):
        logger.error("Valores do sensor Nicla inválidos - ignorando")
        return
    
    agora = time.time()
    # Thread-safe: apenas um thread por vez escreve
    with state_lock:
        system_state["temp"] = temp_val
        system_state["temp_timestamp"] = agora
        system_state["hum"] = hum_val
        system_state["hum_timestamp"] = agora
        system_state["hPa"] = hPa_val
        system_state["hPa_timestamp"] = agora
        system_state["voc_gas"] = voc_val
        system_state["voc_gas_timestamp"] = agora
    
    logger.debug(f"Nicla: T={temp_val}°C, H={hum_val}%, P={hPa_val}hPa, VOC={voc_val}Ω")

def vision_handler(sender, data):
    """Processa pacotes BLE vindos do Arduino Nano 33 (Câmara com IA).
    
    O Arduino envia resultado da classificação IA em formato JSON:
    {"classe_dominante": "Apple Red", "confianca": 92.5}
    
    Args:
        sender: Referência do BLE characteristic
        data (bytes): Payload JSON com classificação
    
    Raises:
        json.JSONDecodeError: Payload não é JSON válido (é capturado e registado)
        ValueError: Confiança fora da gama 0-100 (é rejeitada com aviso)
    """
    payload = data.decode('utf-8').strip()
    try:
        vision_data = json.loads(payload)
        if "classe_dominante" in vision_data and "confianca" in vision_data:
            confianca = float(vision_data["confianca"])
            
            # Validar confiança (0-1 ou 0-100)
            if not (0 <= confianca <= 100):
                logger.warning(f"Confiança fora da gama: {confianca}")
                return
            
            agora = time.time()
            # Thread-safe: apenas um thread por vez escreve
            with state_lock:
                system_state["classe_dominante"] = vision_data["classe_dominante"]
                system_state["confianca"] = confianca
                system_state["vision_timestamp"] = agora
            
            logger.debug(f"Vision: {vision_data['classe_dominante']} ({confianca}%)")
    except json.JSONDecodeError:
        logger.error(f"Payload JSON inválido da Câmara: {payload}")
    except ValueError as e:
        logger.error(f"Erro ao processar confiança: {e}")

async def gerir_conexao(nome_dispositivo, char_uuid, handler):
    """Tarefa assíncrona que mantém conexão BLE estável (com reconexão automática).
    
    Procura por um dispositivo BLE pelo nome e estabelece conexão segura.
    Se desconectar (por qualquer motivo), tenta reconectar automaticamente.
    
    Args:
        nome_dispositivo (str): Nome do device BLE (ex: "RipeRadar")
        char_uuid (str): UUID do characteristic a subscrever
        handler (callable): Função callback para notificações
    
    Raises:
        Nenhuma - erros são capturados, registados e retry automático
    
    Comportamento:
        - Tenta scan com timeout de 10s
        - Se encontra: Conecta com timeout 15s
        - Se desconecta ou erro: Aguarda 1s e retry
        - Rejeita automaticamente após vários erros
    """
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
                logger.error(f"Erro Bluetooth em {nome_dispositivo}: {repr(e)}")
                
        await asyncio.sleep(1)


async def main():
    """Função principal - Orquestra todas as tarefas assíncronas.
    
    Inicia 4 tarefas paralelas:
    1. Gerenciar conexão Nicla (sensor de gases)
    2. Gerenciar conexão Arduino (câmara IA)
    3. Late Fusion Scheduler (publica fusão a cada 2s)
    4. Healthcheck Scheduler (publica heartbeat a cada 30s)
    
    Todas correm em paralelo com asyncio.gather().
    """
    
    logger.info("Orquestrador Assíncrono ativado com MQTT")
    logger.info(f"Intervalo de fusão: {VALIDATION_CONFIG['fusion_interval']}s")
    logger.info(f"Idade máxima de dados: {VALIDATION_CONFIG['required_data_age']}s")
    logger.info(f"Broker MQTT: {MQTT_BROKER}:{MQTT_PORT}")
    logger.info("-" * 80)
    
    # Tarefa 1: Gerenciar conexão Nicla (sensor de gases)
    tarefa_nicla = asyncio.create_task(gerir_conexao(
        CONFIG['devices']['nicla']['name'],
        CONFIG['devices']['nicla']['uuid'],
        nicla_handler
    ))
    await asyncio.sleep(2) 
    
    # Tarefa 2: Gerenciar conexão Arduino (câmara IA)
    tarefa_visao = asyncio.create_task(gerir_conexao(
        CONFIG['devices']['arduino']['name'],
        CONFIG['devices']['arduino']['uuid'],
        vision_handler
    ))
    await asyncio.sleep(1)
    
    # Tarefa 3: Scheduler de Late Fusion (publica a cada N segundos)
    tarefa_fusion = asyncio.create_task(fusion_scheduler())
    await asyncio.sleep(1)
    
    # Tarefa 4: Healthcheck/Heartbeat (monitoriza gateway a cada 30s)
    tarefa_healthcheck = asyncio.create_task(healthcheck_scheduler())
    
    logger.info("Todas as tarefas iniciadas. Aguardando eventos...")
    await asyncio.gather(tarefa_nicla, tarefa_visao, tarefa_fusion, tarefa_healthcheck)

if __name__ == "__main__":
    try:
        logger.info("Iniciando event loop...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Interrupção do utilizador detectada (Ctrl+C)")
    except Exception as e:
        logger.critical(f"Erro fatal: {e}", exc_info=True)
    finally:
        logger.info("Iniciando shutdown gracioso...")
        
        # Aguardar tarefas assíncronas em execução
        tasks = asyncio.all_tasks() if hasattr(asyncio, 'all_tasks') else asyncio.Task.all_tasks()
        for task in tasks:
            task.cancel()
            logger.debug(f"Tarefa cancelada: {task.get_name()}")
        
        # Desconectar MQTT
        try:
            mqtt_client.disconnect()
            mqtt_client.loop_stop()
            logger.info("Cliente MQTT desconectado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao desconectar MQTT: {e}")
        
        logger.info("=" * 80)
        logger.info("Gateway encerrado com sucesso")
        logger.info("=" * 80)