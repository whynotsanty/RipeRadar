#include <SPI.h>
#include <MFRC522.h>
#include <WiFiS3.h>
#include <WiFiSSLClient.h>

// Pinos do Leitor RFID (Ajusta consoante a tua montagem)
#define SS_PIN 10
#define RST_PIN 9
MFRC522 rfid(SS_PIN, RST_PIN);

// Credenciais Wi-Fi
const char* ssid = "MEO-9F2720";
const char* pass = "3499392948";


const char* influx_server = "eu-central-1-1.aws.cloud2.influxdata.com"; 
String token = "Y5_u5FEICS9mkR2Dl2aPZUsX-lihtneYuuYF5ooHET9ncXDPHBDS2xO6mD-ox1358d_qQUOsvyNWRqT4TtJkzw==";
String org = "a00b549847ff266a";
String bucket = "fruit_telemetry";

String uid_chefe = "9E 5C 36 02"; 
String uid_operador = "D2 D5 45 02";
String uidNovaCarga = "37 2C 0E 01";

WiFiSSLClient client;

void setup() {
  Serial.begin(115200);
  SPI.begin();
  rfid.PCD_Init();

  Serial.print("A ligar ao Wi-Fi...");
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi Ligado! Aproxime o cartão.");
}

void loop() {
  // Verifica se há cartão
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return;
  }
  
  // Lê o UID do Cartão
  String cartao_lido = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    cartao_lido += String(rfid.uid.uidByte[i] < 0x10 ? " 0" : " ");
    cartao_lido += String(rfid.uid.uidByte[i], HEX);
  }
  cartao_lido.trim();
  cartao_lido.toUpperCase();
  Serial.println("Cartao lido: " + cartao_lido);

  // Verifica quem é e envia para o InfluxDB
  if (cartao_lido == uid_chefe) {
    Serial.println("Login: Chefe");
    enviarParaInflux("chefe");
  } else if (cartao_lido == uid_operador) {
    Serial.println("Login: Operador");
    enviarParaInflux("operador");
  } else if (cartao_lido == uidNovaCarga) {
    Serial.println("Comando: Registo de Nova Carga");
    enviarOperacaoInflux("nova_carga"); 
  } else {
    Serial.println("Cartão Desconhecido.");
  }

  // Previne múltiplas leituras rápidas do mesmo cartão
  delay(3000); 
}

void enviarParaInflux(String user) {
  if (client.connect(influx_server, 443)) {
    // A estrutura dos dados no InfluxDB: measurement,tag=value field=value
    String postData = "rfid_login,local=pc_windows user_id=\"" + user + "\"";
    
    // Constrói o cabeçalho HTTP
    client.println("POST /api/v2/write?org=" + org + "&bucket=" + bucket + "&precision=s HTTP/1.1");
    client.println("Host: " + String(influx_server));
    client.println("Authorization: Token " + token);
    client.println("Content-Type: text/plain; charset=utf-8");
    client.print("Content-Length: ");
    client.println(postData.length());
    client.println();
    client.println(postData);

    Serial.println("Dados enviados para InfluxDB!");
    client.stop();
  } else {
    Serial.println("Falha na ligação ao InfluxDB.");
  }
}
void enviarOperacaoInflux(String operacao) {
  if (client.connect(influx_server, 443)) {
    // Guarda o evento como uma operação de sistema
    String postData = "rfid_operacoes,local=banca_fruta acao=\"" + operacao + "\"";
    
    client.println("POST /api/v2/write?org=" + org + "&bucket=" + bucket + "&precision=s HTTP/1.1");
    client.println("Host: " + String(influx_server));
    client.println("Authorization: Token " + token);
    client.println("Content-Type: text/plain; charset=utf-8");
    client.print("Content-Length: ");
    client.println(postData.length());
    client.println();
    client.println(postData);
    client.stop();
  }
}