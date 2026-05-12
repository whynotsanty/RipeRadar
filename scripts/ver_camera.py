import serial
import cv2
import numpy as np

PORTA_USB = "/dev/ttyACM0" 
BAUD_RATE = 115200

# Dimensões exatas do modelo Edge Impulse
LARGURA = 64
ALTURA = 64
BYTES_ESPERADOS = LARGURA * ALTURA * 3

def main():
    print(f"[DEBUG] A escutar a porta {PORTA_USB}...")
    try:
        ser = serial.Serial(PORTA_USB, BAUD_RATE, timeout=2)
    except Exception as e:
        print(f"Erro ao abrir a porta: {e}")
        return

    em_captura = False
    # OTIMIZAÇÃO 1: Usar uma lista em vez de string. O método append() é muito mais rápido.
    buffer_hex_list = [] 

    # Pedir o primeiro frame para acordar o "Live USB" no Arduino
    ser.write(b'S')
    ser.flush()

    while True:
        try:
            linha = ser.readline().decode('utf-8').strip()
            
            if linha == "FRAME_START":
                em_captura = True
                buffer_hex_list = [] # Limpa a lista para o novo frame
                continue
                
            if linha == "FRAME_END" and em_captura:
                em_captura = False
                
                try:
                    # Junta a lista toda numa string de uma só vez (muito mais eficiente)
                    hex_string = "".join(buffer_hex_list)
                    bytes_raw = bytes.fromhex(hex_string)
                    
                    # Validação de segurança para evitar crashes se houver perda de dados na série
                    if len(bytes_raw) == BYTES_ESPERADOS:
                        matriz = np.frombuffer(bytes_raw, dtype=np.uint8)
                        imagem_rgb = matriz.reshape((ALTURA, LARGURA, 3))
                        imagem_bgr = cv2.cvtColor(imagem_rgb, cv2.COLOR_RGB2BGR)
                        imagem_zoom = cv2.resize(imagem_bgr, (640, 480), interpolation=cv2.INTER_NEAREST)
                        
                        # OTIMIZAÇÃO 2: Mostrar no ecrã em vez de escrever no disco
                        cv2.imshow("Visao RipeRadar (Nano 33 BLE)", imagem_zoom)
                        cv2.waitKey(1) # Tempo mínimo para o OpenCV atualizar a janela
                    else:
                        print(f"[AVISO] Frame descartado. Faltam dados ({len(bytes_raw)}/{BYTES_ESPERADOS} bytes).")
                        
                except ValueError as ve:
                    print(f"[ERRO] Caracteres hexadecimais inválidos recebidos: {ve}")
                except Exception as e:
                    print(f"[ERRO] Falha ao descodificar imagem: {e}")
                
                # IMAGEM MOSTRADA: Pede logo o próximo frame sem atrasos
                ser.write(b'S')
                ser.flush()
                continue
                
            if em_captura:
                # Adicionar à lista é instantâneo em comparação com concatenar strings
                buffer_hex_list.append(linha)
            else:
                if linha:
                    print(f"[ARDUINO MSG]: {linha}")
                    
        except KeyboardInterrupt:
            print("\n[INFO] Captura interrompida pelo utilizador.")
            break
        except Exception as e:
            print(f"[ERRO CRÍTICO]: {e}")
            break

    ser.close()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()