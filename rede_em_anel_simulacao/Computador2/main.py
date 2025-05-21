import socket
import threading
import time
import random
import zlib
import sys
import os
from datetime import datetime
import logging

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
        gerar_token = linhas[3].strip().lower() == 'true'
        porta = int(porta)
        print(f"Configuração carregada: IP={ip_destino}, Porta={porta}, Apelido={apelido}, Tempo={tempo_token}, Gerador={gerar_token}")
    return ip_destino, porta, apelido, tempo_token, gerar_token

# Carrega configurações do arquivo
ip_destino, porta_destino, apelido, tempo_token, gerar_token = carregar_configuracao()

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs_Computer2.log", mode='w', encoding="utf-8"),  # 'w' para sobrescrever o arquivo
        logging.StreamHandler()
    ]
)

# Configurações globais do sistema
fila_mensagens = []  # Lista de tuplas: (destino, mensagem, reenviado?)
token_presente = False
ultima_passagem_token = time.time()
tempo_maximo_token = 5  # Tempo máximo para o token voltar (em segundos)
tempo_minimo_token = 0.5  # Tempo mínimo entre tokens (em segundos)
nos_ativos = set()  # Conjunto de nós ativos na rede

# Configuração de rede
ip_local = "127.0.0.1"  # Usando localhost para teste
porta_local = porta_destino

# Mapeamento de apelidos para IPs e portas
mapeamento_apelidos = {
    "TODOS": ("127.0.0.1", porta_local)  # Usa a porta local do nó
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

def enviar_udp(ip: str, porta: int, mensagem: str):
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

def registrar_log(mensagem: str, mostrar_terminal: bool = True):
    """
    Registra mensagem com timestamp
    Args:
        mensagem: Texto a ser registrado
        mostrar_terminal: Se True, exibe a mensagem no terminal
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    if mostrar_terminal:
        print(f"\n[{timestamp}] {mensagem}")
    logging.info(mensagem)

def limpar_tela():
    os.system('cls' if os.name == 'nt' else 'clear')

def atualizar_mapeamento(apelido: str, ip: str, porta: int):
    """
    Atualiza o mapeamento de nós ativos
    Args:
        apelido: Nome do nó
        ip: IP do nó
        porta: Porta do nó
    """
    mapeamento_apelidos[apelido] = (ip, porta)
    nos_ativos.add(apelido)
    registrar_log(f"[{apelido}] Nó {apelido} adicionado ao mapeamento: {ip}:{porta}")

def mostrar_status_rede():
    """
    Mostra o status atual da rede
    """
    print("\n" + "="*50)
    print("STATUS DA REDE".center(50))
    print("="*50)
    print("\nNós ativos:")
    for no in sorted(nos_ativos):
        ip, porta = mapeamento_apelidos[no]
        print(f"- {no}: {ip}:{porta}")
    print("\n" + "="*50)

def mostrar_menu():
    limpar_tela()
    print("\n" + "="*50)
    print("REDE EM ANEL - SIMULAÇÃO".center(50))
    print("="*50)
    print(f"\nNó: {apelido}")
    print(f"IP Local: {ip_local}:{porta_local}")
    print(f"Próximo nó: {ip_destino}:{porta_destino}")
    print(f"Gerador de token: {'Sim' if gerar_token else 'Não'}")
    print("\n" + "="*50)
    print("\nOpções:")
    print("1. Enviar mensagem")
    print("2. Ver fila atual")
    print("3. Ver logs")
    print("4. Ver status da rede")
    print("5. Sair")
    print("\n" + "="*50)

def interface_usuario():
    while True:
        try:
            mostrar_menu()
            opcao = input("\nEscolha uma opção: ")
            if opcao == "1":
                enviar_mensagem_usuario()
            elif opcao == "2":
                ver_fila()
            elif opcao == "3":
                ver_logs()
            elif opcao == "4":
                mostrar_status_rede()
                input("\nPressione Enter para continuar...")
            elif opcao == "5":
                logging.info("Encerrando aplicação...")
                print("\nEncerrando aplicação...")
                break
            else:
                print("\nOpção inválida!")
                input("\nPressione Enter para continuar...")
        except Exception as e:
            logging.error(f"Erro na interface: {str(e)}")
            print(f"\nErro: {str(e)}")
            input("\nPressione Enter para continuar...")

def enviar_mensagem_usuario():
    print("\nDestino (apelido ou TODOS): ", end="")
    destino = input().strip()
    
    # Valida se o destino existe
    if destino != "TODOS" and destino not in nos_ativos:
        print(f"\nErro: Destino '{destino}' não existe na rede!")
        print("Destinos disponíveis:", ", ".join(sorted(nos_ativos)))
        input("\nPressione Enter para continuar...")
        return
    
    print("Mensagem: ", end="")
    mensagem = input().strip()
    
    if len(fila_mensagens) >= 10:
        logging.warning("Fila cheia! Máximo de 10 mensagens atingido.")
        print("\nErro: Fila cheia! Máximo de 10 mensagens atingido.")
        input("\nPressione Enter para continuar...")
        return
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensagem_completa = f"{timestamp} | {apelido} -> {destino}: {mensagem}"
    with mutex:
        fila_mensagens.append((destino, mensagem_completa, False))
        logging.info(f"[Fila] Mensagem adicionada: {mensagem_completa}")
        print(f"\n[Fila] Mensagem adicionada.")

def ver_fila():
    print("\n" + "="*50)
    print("FILA DE MENSAGENS".center(50))
    print("="*50)
    if not fila_mensagens:
        print("\nFila vazia")
    else:
        print("\nMensagens pendentes:")
        for i, (dest, msg, reenv) in enumerate(fila_mensagens, 1):
            print(f"{i}. Para: {dest} | Mensagem: {msg} | Reenviado: {reenv}")
    print("\n" + "="*50)
    input("\nPressione Enter para continuar...")

def ver_logs():
    print("\n" + "="*50)
    print("LOGS DO SISTEMA".center(50))
    print("="*50)
    try:
        with open(f"logs_Computer2.log", "r", encoding="utf-8") as f:
            logs = f.readlines()[-20:]  # Mostra últimos 20 logs
            for log in logs:
                print(log.strip())
    except Exception as e:
        print(f"\nErro ao ler logs: {e}")
    print("\n" + "="*50)
    input("\nPressione Enter para continuar...")

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
    registrar_log(f"[{apelido}] Aguardando mensagens e tokens...")
    registrar_log(f"[{apelido}] Próximo nó: {ip_destino}:{porta_destino}")

    # Adiciona o próprio nó ao mapeamento
    atualizar_mapeamento(apelido, ip_local, porta_local)

    while True:
        try:
            dados, endereco = socket_udp.recvfrom(2048)
            mensagem = dados.decode()

            if mensagem == "9000":  # Token
                with lock_token:
                    tempo_atual = time.time()
                    tempo_passado = tempo_atual - ultima_passagem_token
                    
                    if tempo_passado < tempo_minimo_token:
                        registrar_log(f"[{apelido}] ⚠️ ALERTA: Token recebido muito rápido!", mostrar_terminal=False)
                        registrar_log(f"[{apelido}] Tempo desde último token: {tempo_passado:.2f}s", mostrar_terminal=False)
                        continue
                    
                    token_presente = True
                    ultima_passagem_token = tempo_atual
                    registrar_log(f"[{apelido}] ✅ Token recebido - Pronto para enviar mensagens", mostrar_terminal=False)

            elif mensagem.startswith("7777:"):  # Pacote de dados
                _, conteudo = mensagem.split(":", 1)
                controle, origem, destino, crc, texto = conteudo.split(";", 4)

                # Atualiza mapeamento com o nó de origem
                if origem not in mapeamento_apelidos:
                    atualizar_mapeamento(origem, endereco[0], endereco[1])

                # Ignora mensagens próprias
                if origem == apelido:
                    if controle == "naoexiste":
                        registrar_log(f"[{apelido}] Ignorando mensagem própria: {texto}")
                        continue
                    else:
                        print("\n" + "="*50)
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] RETORNO DE MENSAGEM:")
                        print(f"Status: {controle}")
                        print(f"Mensagem: {texto}")
                        print("="*50 + "\n")
                        registrar_log(f"[{apelido}] Pacote retornou: {controle}")
                        with mutex:
                            if fila_mensagens:
                                if controle == "ACK" or controle == "naoexiste":
                                    fila_mensagens.pop(0)
                                    registrar_log(f"[{apelido}] Mensagem entregue/removida.")
                                    # Após remover a mensagem, passa o token
                                    enviar_udp(ip_destino, porta_destino, "9000")
                                    token_presente = False
                                    ultima_passagem_token = time.time()
                                elif controle == "NACK":
                                    destino, texto, reenviado = fila_mensagens[0]
                                    if not reenviado:
                                        fila_mensagens[0] = (destino, texto, True)
                                        registrar_log(f"[{apelido}] NACK recebido. Será retransmitido.")
                                    else:
                                        fila_mensagens[0] = (destino, texto, False)
                                        registrar_log(f"[{apelido}] NACK duplo. Mensagem descartada.")
                                    # Passa o token mesmo com NACK
                                    enviar_udp(ip_destino, porta_destino, "9000")
                                    token_presente = False
                                    ultima_passagem_token = time.time()
                        continue

                if destino == apelido or destino == "TODOS":
                    crc_recalculado = calcular_crc(texto)
                    if int(crc) == crc_recalculado:
                        print("\n" + "="*50)
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] MENSAGEM RECEBIDA:")
                        print(f"De: {origem}")
                        print(f"Para: {destino}")
                        print(f"Conteúdo: {texto}")
                        print(f"Status: CRC OK")
                        print("="*50 + "\n")
                        registrar_log(f"[{apelido}] MENSAGEM RECEBIDA de {origem}: {texto}")
                        resposta = f"7777:ACK;{origem};{apelido};{crc};{texto}"
                    else:
                        print("\n" + "="*50)
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ERRO DE CRC:")
                        print(f"De: {origem}")
                        print(f"Para: {destino}")
                        print(f"Conteúdo: {texto}")
                        print(f"Status: CRC INVÁLIDO")
                        print("="*50 + "\n")
                        registrar_log(f"[{apelido}] Erro de CRC! Enviando NACK para {origem}")
                        resposta = f"7777:NACK;{origem};{apelido};{crc};{texto}"
                    enviar_udp(*mapeamento_apelidos[origem], resposta)

                else:
                    registrar_log(f"[{apelido}] Repassando mensagem para {ip_destino}:{porta_destino}")
                    enviar_udp(ip_destino, porta_destino, mensagem)

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
    global token_presente, fila_mensagens, ultima_passagem_token
    while True:
        try:
            with mutex:
                # Verifica timeout do token
                if gerar_token and time.time() - ultima_passagem_token > tempo_maximo_token:
                    registrar_log(f"[{apelido}] ⚠️ TIMEOUT! Regenerando token...", mostrar_terminal=False)
                    registrar_log(f"[{apelido}] Última passagem do token: {time.time() - ultima_passagem_token:.2f}s atrás", mostrar_terminal=False)
                    enviar_udp(ip_destino, porta_destino, "9000")
                    ultima_passagem_token = time.time()
                    continue

                # Se tem token, processa mensagens
                if token_presente:
                    if fila_mensagens:
                        destino, texto, reenviado = fila_mensagens[0]
                        if reenviado:
                            controle = "naoexiste"
                            mensagem_pronta = texto
                        else:
                            controle = "naoexiste"
                            mensagem_pronta = inserir_erro(texto)
                        
                        # Envia mensagem
                        crc = calcular_crc(mensagem_pronta)
                        pacote = f"7777:{controle};{apelido};{destino};{crc};{mensagem_pronta}"
                        registrar_log(f"[{apelido}] Enviando mensagem para {destino}")
                        enviar_udp(ip_destino, porta_destino, pacote)
                        registrar_log(f"[{apelido}] Mensagem enviada: {mensagem_pronta}")
                        
                        # Aguarda um tempo para a mensagem voltar
                        time.sleep(tempo_token)
                    else:
                        # Se não tem mensagem, passa o token imediatamente
                        registrar_log(f"[{apelido}] Nenhuma mensagem. Enviando token.", mostrar_terminal=False)
                        enviar_udp(ip_destino, porta_destino, "9000")
                        token_presente = False
                        ultima_passagem_token = time.time()
            time.sleep(0.1)  # Pequena pausa para não sobrecarregar a CPU
        except Exception as erro:
            registrar_log(f"[ERRO] Falha no gerenciador: {erro}")

# ================================
# INICIALIZAÇÃO
# ================================
if __name__ == "__main__":
    try:
        logging.info(f"Iniciando nó {apelido} em {ip_local}:{porta_local}")
        
        # Inicia threads
        thread_receptor = threading.Thread(target=receptor)
        thread_gerenciador = threading.Thread(target=gerenciador)
        thread_interface = threading.Thread(target=interface_usuario)
        
        thread_receptor.daemon = True
        thread_gerenciador.daemon = True
        thread_interface.daemon = True
        
        thread_receptor.start()
        thread_gerenciador.start()
        thread_interface.start()
        
        # Mantém o programa rodando
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Encerrando aplicação...")
        print("\nEncerrando aplicação...")
    except Exception as e:
        logging.error(f"Erro fatal: {e}")
        print(f"\nErro fatal: {e}")
    finally:
        if 'socket_udp' in locals():
            socket_udp.close() 