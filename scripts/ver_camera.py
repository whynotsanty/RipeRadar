import serial
import cv2
import numpy as np
import time  # <-- ADICIONADO para gerar nomes únicos para as fotos

# Configurações da porta série (ajusta se necessário, ex: /dev/ttyUSB0)
PORTA_USB = "/dev/ttyACM0" 
BAUD_RATE = 115200

# Dimensões exatas da câmara do Edge Impulse
LARGURA = 64
ALTURA = 64
BYTES_ESPERADOS = LARGURA * ALTURA * 3

def main():
    print(f"[INFO] A tentar ligar à porta {PORTA_USB}...")
    try:
        ser = serial.Serial(PORTA_USB, BAUD_RATE, timeout=2)
    except Exception as e:
        print(f"[ERRO] Não foi possível abrir a porta {PORTA_USB}: {e}")
        return

    em_captura = False
    buffer_hex_list = [] 

    # Limpar qualquer lixo que esteja no buffer antes de começar
    ser.reset_input_buffer()
    print("[INFO] Ligação estabelecida. A aguardar imagens do Arduino...")
    print("[INFO] Prime 's' na janela do vídeo para GUARDAR a imagem atual.")
    print("[INFO] Prime 'q' na janela do vídeo para FECHAR de forma segura.")

    while True:
        try:
            # Ler linha e ignorar caracteres corrompidos para não dar crash
            linha_bruta = ser.readline()
            linha = linha_bruta.decode('utf-8', errors='ignore').strip()
            
            if not linha:
                continue

            if linha == "FRAME_START":
                em_captura = True
                buffer_hex_list = [] # Preparar a lista para um novo frame
                continue
                
            if linha == "FRAME_END" and em_captura:
                em_captura = False
                
                try:
                    # Juntar todos os pedaços hexadecimais recebidos
                    hex_string = "".join(buffer_hex_list)
                    bytes_raw = bytes.fromhex(hex_string)
                    
                    if len(bytes_raw) == BYTES_ESPERADOS:
                        # Reconstruir a imagem a partir dos bytes brutos
                        matriz = np.frombuffer(bytes_raw, dtype=np.uint8)
                        imagem_rgb = matriz.reshape((ALTURA, LARGURA, 3))
                        
                        # OpenCV usa BGR por omissão, precisamos de inverter as cores
                        imagem_bgr = cv2.cvtColor(imagem_rgb, cv2.COLOR_RGB2BGR)
                        
                        # Fazer zoom à imagem (512x512) para não ficar um quadrado minúsculo
                        # INTER_NEAREST mantém os pixéis nítidos e "quadrados" (estilo pixel art)
                        imagem_zoom = cv2.resize(imagem_bgr, (512, 512), interpolation=cv2.INTER_NEAREST)
                        
                        # MOSTRAR EM TEMPO REAL
                        cv2.imshow("RipeRadar - Camara IRT", imagem_zoom)
                        
                        # ======================================================
                        # NOVA LÓGICA DE TECLAS (Guardar 's' e Sair 'q')
                        # ======================================================
                        tecla = cv2.waitKey(1) & 0xFF
                        
                        if tecla == ord('q'):
                            print("[INFO] Encerramento solicitado pelo utilizador.")
                            break
                        elif tecla == ord('s'):
                            # Gera um nome de ficheiro único com timestamp
                            nome_ficheiro = f"captura_irt_{int(time.time())}.jpg"
                            cv2.imwrite(nome_ficheiro, imagem_zoom)
                            print(f"[✓ SUCESSO] Frame guardado como '{nome_ficheiro}'!")
                        # ======================================================

                    else:
                        print(f"[AVISO] Frame incompleto ou corrompido. Descartado ({len(bytes_raw)}/{BYTES_ESPERADOS} bytes).")
                        
                except ValueError as ve:
                    print(f"[ERRO] Falha ao converter valores Hexadecimais: {ve}")
                continue
                
            if em_captura:
                # Acumular os dados de vídeo enviados pelo Arduino
                buffer_hex_list.append(linha)
            else:
                # Imprimir no terminal outros logs (como a precisão da IA ou outputs de debug)
                print(f"[ARDUINO]: {linha}")
                
        except KeyboardInterrupt:
            print("\n[INFO] Script interrompido via terminal (Ctrl+C).")
            break
        except Exception as e:
            print(f"[ERRO CRÍTICO]: {e}")
            break

    # Limpeza final de recursos
    ser.close()
    cv2.destroyAllWindows()
    print("[INFO] Ligação encerrada e janelas fechadas.")

if __name__ == "__main__":
    main()