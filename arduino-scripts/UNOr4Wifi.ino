#include <SPI.h>
#include <MFRC522.h>

// Pinos padrão que já ligaste
#define SS_PIN 10
#define RST_PIN 9

MFRC522 rfid(SS_PIN, RST_PIN); 

void setup() {
  Serial.begin(9600);
  while (!Serial); // Espera que abras o Serial Monitor

  SPI.begin();     // Inicia o barramento SPI
  rfid.PCD_Init(); // Inicia o módulo RC522

  Serial.println("--- RipeRadar: Teste de Diagnóstico RFID ---");
  Serial.println("Passa uma tag ou um cartão no leitor...");
}

void loop() {
  mqttClient.poll();

  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String uid = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      if(rfid.uid.uidByte[i] < 0x10) uid += "0";
      uid += String(rfid.uid.uidByte[i], HEX);
    }
    uid.toUpperCase();

    // Lógica de Decisão
    if (uid == TAG_CAIXA_1) {
      Serial.println("Evento: Nova Caixa de Fruta Detectada");
      mqttClient.beginMessage("riperadar/caixas/ativa");
      mqttClient.print(uid);
      mqttClient.endMessage();
    } 
    else if (uid == CARTAO_OPERADOR || uid == CARTAO_CHEFE) {
      String nivel = (uid == CARTAO_CHEFE) ? "manager" : "operator";
      Serial.println("Evento: Login de " + nivel);
      
      // Envia um JSON simples para o Dashboard
      mqttClient.beginMessage("riperadar/auth/login");
      mqttClient.print("{\"uid\":\"" + uid + "\", \"role\":\"" + nivel + "\"}");
      mqttClient.endMessage();
    }
    else {
      Serial.println("Aviso: Tag desconhecida detectada.");
    }

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    delay(2000); 
  }
}