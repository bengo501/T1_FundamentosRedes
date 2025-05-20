import socket
import threading
import time
import random
import zlib
import sys
import os
from datetime import datetime

# ================================
# CONFIGURAÇÕES INICIAIS
# ================================
def carregar_configuracao():
    """
    Carrega as configurações do arquivo config.txt
    Retorna: IP de destino, porta, apelido, tempo do token e flag de gerador
    """
    with open('config.txt') as arquivo:
        linhas = arquivo.read().splitlines()
        ip_destino, porta = linhas[0].split(":")
        apelido = linhas[1]
        tempo_token = int(linhas[2])
        gerar_token = linhas[3].lower() == 'true'
        porta = int(porta)
    return ip_destino, porta, apelido, tempo_token, gerar_token

# Carrega configurações do arquivo
ip_destino, porta_destino, apelido, tempo_token, gerar_token = carregar_configuracao()

# Configurações globais do sistema
fila_mensagens = []  # Lista de tuplas: (destino, mensagem, reenviado?)
token_presente = False
ultima_passagem_token = time.time()
tempo_maximo_token = 5  # Tempo máximo para o token voltar (em segundos)
tempo_minimo_token = 0.5  # Tempo mínimo entre tokens (em segundos)

# Configuração de rede
ip_local = "127.0.0.1"  # Usando localhost para teste
porta_local = porta_destino

# Mapeamento de apelidos para IPs e portas
mapeamento_apelidos = {
    "Bob": ("127.0.0.1", 6000),
    "Mary": ("127.0.0.1", 6001),
    "John": ("127.0.0.1", 6002),
    "TODOS": ("127.0.0.1", porta_destino)
}

# Locks para sincronização entre threads
mutex = threading.Lock()  # Protege a fila de mensagens
lock_token = threading.Lock()  # Protege o controle do token

# ================================
# FUNÇÕES AUXILIARES
# ================================
def calcular_crc(mensagem: str) -> int:
    """
    Calcula o CRC32 da mensagem para detecção de erros
    Args:
        mensagem: Texto a ser verificado
    Returns:
        Valor CRC32 calculado
    """
    return zlib.crc32(mensagem.encode())

def inserir_erro(mensagem: str, probabilidade: float = 0.2) -> str:
    """
    Insere erro aleatório na mensagem com probabilidade especificada
    Args:
        mensagem: Texto original
        probabilidade: Chance de inserir erro (0.0 a 1.0)
    Returns:
        Mensagem possivelmente modificada
    """
    if random.random() < probabilidade:
        posicao = random.randint(0, len(mensagem) - 1)
        return mensagem[:posicao] + chr((ord(mensagem[posicao]) + 1) % 128) + mensagem[posicao + 1:]
    return mensagem

def enviar_mensagem(ip: str, porta: int, mensagem: str):
    """
    Envia mensagem UDP para o destino especificado
    Args:
        ip: Endereço IP de destino
        porta: Porta de destino
        mensagem: Texto a ser enviado
    """
    try:
        socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        socket_udp.sendto(mensagem.encode(), (ip, porta))
        socket_udp.close()
    except Exception as erro:
        print(f"[ERRO] Falha ao enviar mensagem: {erro}")

def registrar_log(mensagem: str):
    """
    Registra mensagem com timestamp
    Args:
        mensagem: Texto a ser registrado
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {mensagem}")

# ================================
# THREAD DE RECEPÇÃO
# ================================
def receptor():
    """
    Thread responsável por receber mensagens e tokens
    Gerencia a chegada de tokens e pacotes de dados
    """
    global token_presente, ultima_passagem_token, fila_mensagens
    socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_udp.bind((ip_local, porta_local))
    registrar_log(f"[{apelido}] Receptor ativo em {ip_local}:{porta_local}")

    while True:
        try:
            dados, endereco = socket_udp.recvfrom(2048)
            mensagem = dados.decode()

            if mensagem == "9000":  # Token
                with lock_token:
                    tempo_atual = time.time()
                    tempo_passado = tempo_atual - ultima_passagem_token
                    
                    if tempo_passado < tempo_minimo_token:
                        registrar_log(f"[{apelido}] ALERTA: Token recebido muito rápido! ({tempo_passado:.2f}s)")
                        continue
                    
                    token_presente = True
                    ultima_passagem_token = tempo_atual
                    registrar_log(f"[{apelido}] Token recebido")

            elif mensagem.startswith("7777:"):  # Pacote de dados
                _, conteudo = mensagem.split(":", 1)
                controle, origem, destino, crc, texto = conteudo.split(";", 4)

                if destino == apelido or destino == "TODOS":
                    crc_recalculado = calcular_crc(texto)
                    if int(crc) == crc_recalculado:
                        registrar_log(f"[{apelido}] Mensagem de {origem}: {texto} [CRC OK]")
                        resposta = f"7777:ACK;{origem};{apelido};{crc};{texto}"
                    else:
                        registrar_log(f"[{apelido}] Erro de CRC! Enviando NACK para {origem}")
                        resposta = f"7777:NACK;{origem};{apelido};{crc};{texto}"
                    enviar_mensagem(*mapeamento_apelidos[origem], resposta)

                elif origem == apelido:
                    registrar_log(f"[{apelido}] Pacote retornou: {controle}")
                    with mutex:
                        if fila_mensagens:
                            if controle == "ACK" or controle == "naoexiste":
                                fila_mensagens.pop(0)
                                registrar_log(f"[{apelido}] Mensagem entregue/removida.")
                            elif controle == "NACK":
                                destino, texto, reenviado = fila_mensagens[0]
                                if not reenviado:
                                    fila_mensagens[0] = (destino, texto, True)
                                    registrar_log(f"[{apelido}] NACK recebido. Será retransmitido.")
                                else:
                                    fila_mensagens[0] = (destino, texto, False)
                                    registrar_log(f"[{apelido}] NACK duplo. Mensagem descartada.")
                else:
                    enviar_mensagem(ip_destino, porta_destino, mensagem)

        except Exception as erro:
            registrar_log(f"[ERRO] Falha na recepção: {erro}")

# ================================
# THREAD DO GERENCIADOR
# ================================
def gerenciador():
    """
    Thread responsável por gerenciar o token e enviar mensagens
    Controla o fluxo de dados na rede em anel
    """
    global token_presente, fila_mensagens
    while True:
        try:
            with mutex:
                if gerar_token and time.time() - ultima_passagem_token > tempo_maximo_token:
                    registrar_log(f"[{apelido}] Timeout! Regenerando token...")
                    enviar_mensagem(ip_destino, porta_destino, "9000")
                    ultima_passagem_token = time.time()

                if token_presente:
                    if fila_mensagens:
                        destino, texto, reenviado = fila_mensagens[0]
                        if reenviado:
                            controle = "naoexiste"
                            mensagem_pronta = texto
                        else:
                            controle = "naoexiste"
                            mensagem_pronta = inserir_erro(texto)
                        crc = calcular_crc(mensagem_pronta)
                        pacote = f"7777:{controle};{apelido};{destino};{crc};{mensagem_pronta}"
                        enviar_mensagem(ip_destino, porta_destino, pacote)
                        registrar_log(f"[{apelido}] Enviando para {destino}: {mensagem_pronta} [{controle}]")
                    else:
                        registrar_log(f"[{apelido}] Nenhuma mensagem. Enviando token.")
                        enviar_mensagem(ip_destino, porta_destino, "9000")
                    token_presente = False
            time.sleep(tempo_token)
        except Exception as erro:
            registrar_log(f"[ERRO] Falha no gerenciador: {erro}")

# ================================
# INTERFACE DE MENSAGENS
# ================================
def interface():
    """
    Interface principal do programa
    Permite enviar mensagens e visualizar a fila
    """
    while True:
        try:
            print("\nOpções:")
            print("1. Enviar mensagem")
            print("2. Ver fila atual")
            print("3. Sair")
            opcao = input("Escolha uma opção: ")

            if opcao == "1":
                destino = input("Destino (apelido ou TODOS): ")
                texto = input("Mensagem: ")
                with mutex:
                    if len(fila_mensagens) < 10:
                        fila_mensagens.append((destino, texto, False))
                        registrar_log("[Fila] Mensagem adicionada.")
                    else:
                        registrar_log("[Fila] Limite atingido (máx 10 mensagens).")
            elif opcao == "2":
                with mutex:
                    if fila_mensagens:
                        print("\nFila atual:")
                        for i, (dest, msg, reenv) in enumerate(fila_mensagens, 1):
                            print(f"{i}. Para: {dest} | Mensagem: {msg} | Reenviado: {reenv}")
                    else:
                        print("\nFila vazia")
            elif opcao == "3":
                registrar_log("Encerrando aplicação...")
                os._exit(0)
            else:
                print("Opção inválida!")
        except Exception as erro:
            registrar_log(f"[ERRO] Falha na interface: {erro}")

# ================================
# INICIALIZAÇÃO
# ================================
if __name__ == "__main__":
    try:
        print(f"\n=== Rede em Anel - {apelido} ===")
        print(f"IP Local: {ip_local}:{porta_local}")
        print(f"Próximo nó: {ip_destino}:{porta_destino}")
        print(f"Gerador de token: {'Sim' if gerar_token else 'Não'}")
        print("==============================\n")

        # Inicia threads
        threading.Thread(target=receptor, daemon=True).start()
        threading.Thread(target=gerenciador, daemon=True).start()
        
        # Inicia interface principal
        interface()
    except KeyboardInterrupt:
        registrar_log("\nEncerrando aplicação...")
        sys.exit(0)
    except Exception as erro:
        registrar_log(f"[ERRO] Falha fatal: {erro}")
        sys.exit(1) 