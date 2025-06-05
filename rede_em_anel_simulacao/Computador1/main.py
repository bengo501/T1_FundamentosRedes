"""
Implementação de uma rede em anel usando UDP.
Este programa simula uma rede local em anel onde as máquinas se comunicam através de tokens
e pacotes de dados, implementando controle de erro e retransmissão.
"""

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
    Carrega as configurações do arquivo config.txt.
    O arquivo deve seguir o formato:
    <ip_destino_do_token>:porta
    <apelido_da_máquina_atual>
    <tempo_token>
    <token>
    <tempo_maximo_token> (opcional)
    Returns:
        tuple: (ip_destino, porta, apelido, tempo_token, gerar_token, tempo_maximo_token)
            - ip_destino: IP da máquina à direita no anel
            - porta: Porta da máquina à direita
            - apelido: Nome da máquina atual
            - tempo_token: Tempo que a máquina fica com o token
            - gerar_token: Se esta máquina é a geradora do token
            - tempo_maximo_token: Tempo máximo para o token voltar
    """
    with open('config.txt') as arquivo:
        linhas = arquivo.read().splitlines()
        ip_destino, porta = linhas[0].split(":")
        apelido = linhas[1]
        tempo_token = int(linhas[2])
        gerar_token = linhas[3].strip().lower() == 'true'
        tempo_maximo_token = int(linhas[4]) if len(linhas) > 4 else 5
        porta = int(porta)
        print(f"Configuração carregada: IP={ip_destino}, Porta={porta}, Apelido={apelido}, Tempo={tempo_token}, Gerador={gerar_token}, Timeout={tempo_maximo_token}")
    return ip_destino, porta, apelido, tempo_token, gerar_token, tempo_maximo_token

# Carrega configurações do arquivo
ip_destino, porta_destino, apelido, tempo_token, gerar_token, tempo_maximo_token = carregar_configuracao()
# Configuração de logging - Define formato e arquivo de log
logging.basicConfig(
    level=logging.INFO,  # Nível de log: INFO para mensagens informativas
    format='%(asctime)s - %(levelname)s - %(message)s',  # Formato: data/hora - nível - mensagem
    handlers=[
        logging.FileHandler(f"logs_Computer1.log", mode='w', encoding="utf-8")  # Arquivo de log com codificação UTF-8
    ]
)
# Configurações globais do sistema
fila_mensagens = []  # Lista de tuplas: (destino, mensagem, reenviado?) - Armazena mensagens pendentes
token_presente = False  # Flag que indica se o nó possui o token
ultima_passagem_token = time.time()  # Timestamp da última vez que o token passou por este nó
tempo_minimo_token = 0.5  # Tempo mínimo entre tokens (em segundos) - Evita sobrecarga
nos_ativos = set()  # Conjunto de nós ativos na rede - Usado para descoberta de nós

# Configuração de rede - Usando localhost para simulação local
ip_local = "127.0.0.1"  # IP local para testes
porta_local = 6000  # Porta padrão para este nó

# Mapeamento de apelidos para IPs e portas - Inicializa com o próprio nó
mapeamento_apelidos = {
    "TODOS": ("127.0.0.1", porta_local)  # Usa a porta local do nó para broadcast
}
# Locks para sincronização entre threads
mutex = threading.Lock()  # Protege a fila de mensagens de acesso concorrente
lock_token = threading.Lock()  # Protege o controle do token de acesso concorrente

# ================================
# FUNÇÕES AUXILIARES
# ================================
def calcular_crc(mensagem: str) -> int:
    """
    Calcula o CRC32 da mensagem para detecção de erros.
    Usa zlib para cálculo eficiente do CRC32.
        Args: mensagem: Texto a ser verificado
        Returns: int: Valor CRC32 calculado
    """
    return zlib.crc32(mensagem.encode())  # Converte para bytes e calcula CRC32

def inserir_erro(mensagem: str, probabilidade: float = 0.2) -> str:
    """
    Insere erro aleatório na mensagem com probabilidade especificada.
    Usado para simular erros de transmissão.
    Args:       mensagem: Texto original
                probabilidade: Chance de inserir erro (0.0 a 1.0)
    Returns:    str: Mensagem possivelmente modificada
    """
    if random.random() < probabilidade:  # Gera número aleatório entre 0 e 1
        posicao = random.randint(0, len(mensagem) - 1)  # Escolhe posição aleatória
        # Modifica o caractere na posição escolhida
        return mensagem[:posicao] + chr((ord(mensagem[posicao]) + 1) % 128) + mensagem[posicao + 1:]
    return mensagem

def enviar_udp(ip: str, porta: int, mensagem: str):
    """
    Envia mensagem UDP para o destino especificado.
    Cria socket temporário para cada envio.
    Args:   ip: Endereço IP de destino
            porta: Porta de destino
            mensagem: Texto a ser enviado
    """
    try:
        socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Cria socket UDP
        socket_udp.sendto(mensagem.encode(), (ip, porta))  # Envia mensagem codificada
        socket_udp.close()  # Fecha socket após envio
        if mensagem == "9000":  # Se for token
            registrar_log(f"[{apelido}] Token enviado com sucesso para {ip}:{porta}", mostrar_terminal=False)
        else:  # Se for mensagem normal
            registrar_log(f"[{apelido}] Mensagem enviada com sucesso para {ip}:{porta}", mostrar_terminal=False)
    except Exception as erro:
        if mensagem == "9000":  # Erro no envio do token
            registrar_log(f"[{apelido}] ERRO ao enviar token para {ip}:{porta} - {erro}")
        else:  # Erro no envio de mensagem
            registrar_log(f"[{apelido}] ERRO ao enviar mensagem para {ip}:{porta} - {erro}")
        print(f"[ERRO] Falha ao enviar mensagem: {erro}")  # Feedback imediato para usuário

def registrar_log(mensagem: str, mostrar_terminal: bool = False):
    """
    Registra mensagem com timestamp no arquivo de log.
    Pode opcionalmente mostrar no terminal.
    Args:   mensagem: Texto a ser registrado
            mostrar_terminal: Se True, exibe a mensagem no terminal
    """
    timestamp = datetime.now().strftime("%H:%M:%S")  # Formata hora atual
    if mostrar_terminal:
        print(f"\n[{timestamp}] {mensagem}")  # Mostra no terminal se solicitado
    logging.info(mensagem)  # Registra no arquivo de log

def limpar_tela():
    """
    Limpa a tela do terminal.
    Usa comando específico do sistema operacional.
    """
    os.system('cls' if os.name == 'nt' else 'clear')  # cls para Windows, clear para Unix

def atualizar_mapeamento(apelido: str, ip: str, porta: int):
    """
    Atualiza o mapeamento de nós ativos na rede.
    Mantém registro de todos os nós conhecidos.
    Args:   apelido: Nome do nó
            ip: IP do nó
            porta: Porta do nó
    """
    mapeamento_apelidos[apelido] = (ip, porta)  # Atualiza mapeamento
    nos_ativos.add(apelido)  # Adiciona à lista de nós ativos
    registrar_log(f"[{apelido}] Nó {apelido} adicionado ao mapeamento: {ip}:{porta}")  # Registra atualização

def mostrar_status_rede():
    """
    Mostra o status atual da rede, incluindo todos os nós ativos e suas informações.
    Exibe uma tabela formatada com os nós ativos e seus respectivos endereços IP e portas.
    """
    print("\n" + "="*50)  # Linha separadora superior
    print("STATUS DA REDE".center(50))  # Título centralizado
    print("="*50)  # Linha separadora inferior
    print("\nNós ativos:")  # Cabeçalho da lista
    for no in sorted(nos_ativos):  # Itera sobre nós ordenados alfabeticamente
        ip, porta = mapeamento_apelidos[no]  # Obtém endereço do nó
        print(f"- {no}: {ip}:{porta}")  # Exibe informações do nó
    print("\n" + "="*50)  # Linha separadora final

def mostrar_status_anel():
    """
    Mostra o status atual do anel, incluindo:
    - Estado do token (presente/ausente)
    - Tempo desde a última passagem do token
    - Lista de máquinas ativas
    - Estado da fila de mensagens
    - Detalhes da próxima mensagem a ser enviada
    """
    print("\n" + "="*50)  # Linha separadora superior
    print("STATUS DO ANEL".center(50))  # Título centralizado
    print("="*50)  # Linha separadora inferior
    # Exibe estado do token
    print(f"\nToken: {'Presente' if token_presente else 'Ausente'}")
    print(f"Última passagem: {time.time() - ultima_passagem_token:.2f}s atrás")
    # Lista máquinas ativas
    print(f"\nMáquinas ativas:")
    for no in sorted(nos_ativos):  # Itera sobre nós ordenados
        ip, porta = mapeamento_apelidos[no]
        print(f"- {no}: {ip}:{porta}")
    # Exibe estado da fila
    print(f"\nFila de mensagens: {len(fila_mensagens)} mensagens")
    if fila_mensagens:  # Se houver mensagens na fila
        print("\nPróxima mensagem:")
        destino, texto, reenviado = fila_mensagens[0]  # Obtém primeira mensagem
        print(f"Para: {destino}")
        print(f"Conteúdo: {texto}")
        print(f"Status: {'Reenviando' if reenviado else 'Nova'}")
    print("="*50)  # Linha separadora final

def mostrar_menu():
    """
    Exibe o menu principal da aplicação com todas as opções disponíveis.
    Mostra informações do nó atual e opções de interação.
    """
    limpar_tela()  # Limpa a tela antes de mostrar menu
    print("\n" + "="*50)  # Linha separadora superior
    print("REDE EM ANEL - SIMULAÇÃO".center(50))  # Título centralizado
    print("="*50)  # Linha separadora inferior
    # Exibe informações do nó
    print(f"\nNó: {apelido}")
    print(f"IP Local: {ip_local}:{porta_local}")
    print(f"Próximo nó: {ip_destino}:{porta_destino}")
    print(f"Gerador de token: {'Sim' if gerar_token else 'Não'}")
    
    print("\n" + "="*50)  # Linha separadora
    print("\nOpções:")  # Lista de opções
    print("1. Enviar mensagem")
    print("2. Ver fila atual")
    print("3. Ver logs")
    print("4. Ver status da rede")
    print("5. Enviar mensagem com ERRO (NACK)")
    print("6. Ver status do anel")
    print("7. Sair")
    print("\n" + "="*50)  # Linha separadora final

def enviar_mensagem_usuario():
    """
    Interface para o usuário enviar uma mensagem.
    Solicita o destino e a mensagem, valida o destino e adiciona à fila.
    A fila tem limite de 10 mensagens.
    """
    print("\nDestino (apelido ou TODOS): ", end="")  # Solicita destino
    destino = input().strip()  # Lê e limpa entrada
    # Valida destino
    if destino != "TODOS" and destino not in nos_ativos:
        print(f"\nErro: Destino '{destino}' não existe na rede!")
        print("Destinos disponíveis:", ", ".join(sorted(nos_ativos)))
        input("\nPressione Enter para continuar...")
        return
    
    print("Mensagem: ", end="")  # Solicita mensagem
    mensagem = input().strip()  # Lê e limpa entrada
    # Verifica limite da fila
    if len(fila_mensagens) >= 10:
        logging.warning("Fila cheia! Máximo de 10 mensagens atingido.")
        print("\nErro: Fila cheia! Máximo de 10 mensagens atingido.")
        input("\nPressione Enter para continuar...")
        return
    # Prepara e adiciona mensagem à fila
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensagem_completa = f"{timestamp} | {apelido} -> {destino}: {mensagem}"
    with mutex:  # Protege acesso à fila
        fila_mensagens.append((destino, mensagem_completa, False))  # Adiciona à fila
        logging.info(f"[Fila] Mensagem adicionada: {mensagem_completa}")  # Registra no log
        print(f"\n[Fila] Mensagem adicionada.")  # Feedback ao usuário
        input("\nPressione Enter para continuar...")

def ver_fila():
    """
    Exibe o conteúdo atual da fila de mensagens.
    Mostra todas as mensagens pendentes com seus destinos e status.
    """
    print("\n" + "="*50)  # Linha separadora superior
    print("FILA DE MENSAGENS".center(50))  # Título centralizado
    print("="*50)  # Linha separadora inferior
    
    if not fila_mensagens:  # Verifica se fila está vazia
        print("\nFila vazia")
    else:
        print("\nMensagens pendentes:")  # Lista mensagens
        for i, (dest, msg, reenv) in enumerate(fila_mensagens, 1):  # Enumera mensagens
            print(f"{i}. Para: {dest} | Mensagem: {msg} | Reenviado: {reenv}")
    
    print("\n" + "="*50)  # Linha separadora final
    input("\nPressione Enter para continuar...")  # Aguarda confirmação

def ver_logs():
    """
    Exibe os últimos 20 logs do sistema.
    Mostra o histórico de eventos e operações realizadas.
    """
    print("\n" + "="*50)  # Linha separadora superior
    print("LOGS DO SISTEMA".center(50))  # Título centralizado
    print("="*50)  # Linha separadora inferior
    
    try:
        with open(f"logs_Computer1.log", "r", encoding="utf-8") as f:
            logs = f.readlines()[-20:]  # Lê últimos 20 logs
            for log in logs:
                print(log.strip())  # Exibe cada log
    except Exception as e:
        print(f"\nErro ao ler logs: {e}")  # Trata erro de leitura
    
    print("\n" + "="*50)  # Linha separadora final
    input("\nPressione Enter para continuar...")  # Aguarda confirmação

def enviar_mensagem_com_erro():
    """
    Interface para enviar uma mensagem com erro forçado.
    Similar ao envio normal, mas adiciona um erro forçado na mensagem
    para testar o mecanismo de NACK e retransmissão.
    """
    print("\nDestino (apelido ou TODOS): ", end="")  # Solicita destino
    destino = input().strip()  # Lê e limpa entrada
    # Valida destino
    if destino != "TODOS" and destino not in nos_ativos:
        print(f"\nErro: Destino '{destino}' não existe na rede!")
        print("Destinos disponíveis:", ", ".join(sorted(nos_ativos)))
        input("\nPressione Enter para continuar...")
        return
    
    print("Mensagem: ", end="")  # Solicita mensagem
    mensagem = input().strip()  # Lê e limpa entrada
    # Verifica limite da fila
    if len(fila_mensagens) >= 10:
        logging.warning("Fila cheia! Máximo de 10 mensagens atingido.")
        print("\nErro: Fila cheia! Máximo de 10 mensagens atingido.")
        input("\nPressione Enter para continuar...")
        return
    # Prepara mensagem com erro forçado
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensagem_completa = f"{timestamp} | {apelido} -> {destino}: {mensagem}"
    mensagem_com_erro = mensagem_completa + "ERRO_FORÇADO"
    # Adiciona à fila
    with mutex:
        fila_mensagens.append((destino, mensagem_com_erro, False))
        print("\n" + "="*50)
        print("MENSAGEM COM ERRO FORÇADO")
        print("="*50)
        print(f"Destino: {destino}")
        print(f"Mensagem: {mensagem_completa}")
        print(f"Status: Aguardando envio com erro forçado")
        print("="*50 + "\n")
        registrar_log(f"[{apelido}] Mensagem com erro forçado adicionada: {mensagem_completa}")
        registrar_log(f"[{apelido}] Status: Aguardando envio com erro forçado")
        input("\nPressione Enter para continuar...")

def interface_usuario():
    """
    Loop principal da interface do usuário.
    Processa as opções do menu e executa as ações correspondentes.
    Mantém o programa rodando até que o usuário escolha sair.
    """
    while True:
        try:
            mostrar_menu()  # Exibe menu principal
            opcao = input("\nEscolha uma opção: ")  # Lê opção do usuário
            # Processa opção escolhida
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
                enviar_mensagem_com_erro()
            elif opcao == "6":
                mostrar_status_anel()
                input("\nPressione Enter para continuar...")
            elif opcao == "7":
                logging.info("Encerrando aplicação...")  # Registra encerramento
                print("\nEncerrando aplicação...")
                break
            else:
                print("\nOpção inválida!")  # Feedback de erro
                input("\nPressione Enter para continuar...")
        except Exception as e:
            logging.error(f"Erro na interface: {str(e)}")  # Registra erro
            print(f"\nErro: {str(e)}")  # Feedback de erro
            input("\nPressione Enter para continuar...")
# ================================
# THREAD DE RECEPÇÃO
# ================================
def receptor():
    """
    Thread responsável por receber mensagens e tokens.
    Funcionalidades:
    1. Recebe e processa mensagens UDP
    2. Gerencia a chegada de tokens
    3. Processa pacotes de dados
    4. Implementa o protocolo de controle de erro
    5. Gerencia a descoberta de nós na rede
    """
    global token_presente, ultima_passagem_token, fila_mensagens
    # Inicializa socket UDP para recebimento
    socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_udp.bind((ip_local, porta_local))
    registrar_log(f"[{apelido}] Receptor ativo em {ip_local}:{porta_local}")
    registrar_log(f"[{apelido}] Aguardando mensagens e tokens...")
    registrar_log(f"[{apelido}] Próximo nó: {ip_destino}:{porta_destino}")
    # Inicializa mapeamento com próprio nó
    atualizar_mapeamento(apelido, ip_local, porta_local)
    # Envia mensagem de descoberta para iniciar mapeamento
    mensagem_descoberta = f"DISCOVER:{apelido}:{ip_local}:{porta_local}"
    enviar_udp(ip_destino, porta_destino, mensagem_descoberta)
    registrar_log(f"[{apelido}] Enviando mensagem de descoberta para {ip_destino}:{porta_destino}")

    while True:
        try:
            # Recebe mensagem UDP
            dados, endereco = socket_udp.recvfrom(2048)
            mensagem = dados.decode()
            # Processa mensagem de descoberta
            if mensagem.startswith("DISCOVER:"):
                _, nome, ip, porta = mensagem.split(":")
                porta = int(porta)
                if nome != apelido:  # Ignora mensagens próprias
                    atualizar_mapeamento(nome, ip, porta)
                    registrar_log(f"[{apelido}] Nó descoberto: {nome} ({ip}:{porta})")
                    # Repassa descoberta para manter anel
                    enviar_udp(ip_destino, porta_destino, mensagem)
            # Processa token
            elif mensagem == "9000":
                with lock_token:
                    tempo_atual = time.time()
                    tempo_passado = tempo_atual - ultima_passagem_token
                    # Verifica se token chegou muito rápido (possível duplicação)
                    if tempo_passado < tempo_minimo_token:
                        registrar_log(f"[{apelido}] ALERTA: Token recebido muito rápido!")
                        registrar_log(f"[{apelido}] Tempo desde último token: {tempo_passado:.2f}s")
                        registrar_log(f"[{apelido}] DETECTADO: Múltiplos tokens na rede!")
                        # Resolve múltiplos tokens
                        if token_presente:
                            registrar_log(f"[{apelido}] Removendo token duplicado...")
                            time.sleep(random.uniform(0.1, 0.5))  # Evita colisões
                            enviar_udp(ip_destino, porta_destino, "9000")
                            token_presente = False
                            ultima_passagem_token = tempo_atual
                            continue
                    # Atualiza estado do token
                    token_presente = True
                    ultima_passagem_token = tempo_atual
                    registrar_log(f"[{apelido}] Token recebido de {ip_destino}:{porta_destino}")
                    registrar_log(f"[{apelido}] TOKEN: Atualmente em {apelido}")
                    time.sleep(3)  # Aguarda tempo do token
            # Processa pacote de dados
            elif mensagem.startswith("7777:"):
                _, conteudo = mensagem.split(":", 1)
                controle, origem, destino, crc, texto = conteudo.split(";", 4)
                registrar_log(f"[{apelido}] PACOTE: {origem} -> {destino} | Status: {controle}")
                # Atualiza mapeamento com origem
                if origem not in mapeamento_apelidos:
                    atualizar_mapeamento(origem, endereco[0], endereco[1])
                # Processa mensagem própria (retorno)
                if origem == apelido:
                    if controle == "naoexiste":
                        registrar_log(f"[{apelido}] Ignorando mensagem própria: {texto}")
                        continue
                    else:
                        # Exibe retorno da mensagem
                        print("\n" + "="*50)
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] RETORNO DE MENSAGEM:")
                        print(f"Status: {controle}")
                        print(f"Mensagem: {texto}")
                        print("="*50 + "\n")
                        # Processa diferentes tipos de retorno
                        if controle == "NACK":
                            registrar_log(f"[{apelido}] NACK recebido - Erro detectado no destino")
                            registrar_log(f"[{apelido}] Iniciando tentativa de retransmissão")
                        elif controle == "ACK":
                            registrar_log(f"[{apelido}] ACK recebido - Mensagem entregue com sucesso")
                        elif controle == "naoexiste":
                            registrar_log(f"[{apelido}] Destino não encontrado na rede")
                        # Atualiza fila baseado no retorno
                        with mutex:
                            if fila_mensagens:
                                if controle == "ACK" or controle == "naoexiste":
                                    fila_mensagens.pop(0)  # Remove mensagem confirmada
                                    registrar_log(f"[{apelido}] Mensagem removida da fila após confirmação")
                                    enviar_udp(ip_destino, porta_destino, "9000")  # Passa token
                                    token_presente = False
                                    ultima_passagem_token = time.time()
                                elif controle == "NACK":
                                    destino, texto, reenviado = fila_mensagens[0]
                                    if not reenviado:
                                        # Primeira tentativa de retransmissão
                                        fila_mensagens[0] = (destino, texto, True)
                                        registrar_log(f"[{apelido}] Primeiro NACK - Preparando retransmissão")
                                    else:
                                        # Descarta após falha na retransmissão
                                        fila_mensagens[0] = (destino, texto, False)
                                        registrar_log(f"[{apelido}] NACK duplo - Mensagem descartada")
                                    enviar_udp(ip_destino, porta_destino, "9000")
                                    token_presente = False
                                    ultima_passagem_token = time.time()
                        continue
                # Processa mensagem destinada a este nó
                if destino == apelido or destino == "TODOS":
                    # Verifica integridade da mensagem
                    crc_recalculado = calcular_crc(texto)
                    if int(crc) == crc_recalculado:
                        # Mensagem válida
                        print("\n" + "="*50)
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] MENSAGEM RECEBIDA:")
                        print(f"De: {origem}")
                        print(f"Para: {destino}")
                        print(f"Conteúdo: {texto}")
                        print(f"Status: CRC OK")
                        print("="*50 + "\n")
                        registrar_log(f"[{apelido}] MENSAGEM RECEBIDA de {origem}: {texto}")
                        # Trata erro forçado se presente
                        if "ERRO_FORÇADO" in texto:
                            registrar_log(f"[{apelido}] ERRO FORÇADO detectado")
                            texto_tratado = texto.replace("ERRO_FORÇADO", "")
                            crc_tratado = calcular_crc(texto_tratado)
                            resposta = f"7777:ACK;{origem};{apelido};{crc_tratado};{texto_tratado}"
                        else:
                            resposta = f"7777:ACK;{origem};{apelido};{crc};{texto}"
                    else:
                        # Erro de CRC detectado
                        print("\n" + "="*50)
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ERRO DE CRC:")
                        print(f"De: {origem}")
                        print(f"Para: {destino}")
                        print(f"Conteúdo: {texto}")
                        print(f"Status: CRC INVÁLIDO")
                        print("="*50 + "\n")
                        registrar_log(f"[{apelido}] ERRO DE CRC detectado na mensagem de {origem}")
                        resposta = f"7777:NACK;{origem};{apelido};{crc};{texto}"
                    enviar_udp(*mapeamento_apelidos[origem], resposta)

                else:
                    # Repassa mensagem para próximo nó
                    registrar_log(f"[{apelido}] Repassando mensagem para {ip_destino}:{porta_destino}")
                    enviar_udp(ip_destino, porta_destino, mensagem)

        except Exception as erro:
            registrar_log(f"[{apelido}] ERRO na recepção: {erro}")
# ================================
# THREAD DO GERENCIADOR
# ================================
def gerenciador():
    """
    Thread responsável por gerenciar o token e enviar mensagens.
    Funcionalidades:
    1. Controla o fluxo do token na rede
    2. Gerencia o envio de mensagens
    3. Implementa o controle de timeout do token
    4. Gerencia a retransmissão de mensagens
    """
    global token_presente, fila_mensagens, ultima_passagem_token
    while True:
        try:
            with mutex:
                # Verifica timeout do token
                if gerar_token and time.time() - ultima_passagem_token > tempo_maximo_token:
                    registrar_log(f"[{apelido}] TIMEOUT! Regenerando token...")
                    registrar_log(f"[{apelido}] Última passagem do token: {time.time() - ultima_passagem_token:.2f}s atrás")
                    enviar_udp(ip_destino, porta_destino, "9000")
                    ultima_passagem_token = time.time()
                    continue
                # Processa mensagens quando tem token
                if token_presente:
                    if fila_mensagens:
                        destino, texto, reenviado = fila_mensagens[0]
                        if reenviado:
                            # Retransmissão de mensagem
                            controle = "naoexiste"
                            mensagem_pronta = texto
                            registrar_log(f"[{apelido}] Retransmitindo mensagem para {destino}")
                        else:
                            # Nova mensagem
                            controle = "naoexiste"
                            mensagem_pronta = inserir_erro(texto)
                            registrar_log(f"[{apelido}] Enviando nova mensagem para {destino}")
                        # Envia mensagem
                        crc = calcular_crc(mensagem_pronta)
                        pacote = f"7777:{controle};{apelido};{destino};{crc};{mensagem_pronta}"
                        registrar_log(f"[{apelido}] Tentando enviar mensagem para {destino}")
                        try:
                            enviar_udp(ip_destino, porta_destino, pacote)
                            if "ERRO_FORÇADO" in mensagem_pronta:
                                registrar_log(f"[{apelido}] Mensagem com erro forçado enviada")
                            else:
                                registrar_log(f"[{apelido}] Mensagem enviada com sucesso: {mensagem_pronta}")
                            if not reenviado:
                                fila_mensagens.pop(0)
                        except Exception as erro:
                            registrar_log(f"[{apelido}] Falha ao enviar mensagem: {erro}")
                            registrar_log(f"[{apelido}] Mensagem mantida na fila para nova tentativa")
                        # Aguarda tempo do token
                        time.sleep(tempo_token)
                    else:
                        # Passa token se não há mensagens
                        registrar_log(f"[{apelido}] Nenhuma mensagem. Enviando token para {ip_destino}:{porta_destino}.")
                        enviar_udp(ip_destino, porta_destino, "9000")
                        token_presente = False
                        ultima_passagem_token = time.time()
            time.sleep(0.1)  # Evita sobrecarga da CPU
        except Exception as erro:
            registrar_log(f"[{apelido}] ERRO no gerenciador: {erro}")
# ================================
# INICIALIZAÇÃO
# ================================
if __name__ == "__main__":
    """
    Ponto de entrada principal do programa.
    Inicialização:
    1. Carrega configurações do arquivo
    2. Configura logging
    3. Inicializa variáveis globais
    4. Inicia threads principais
    Threads iniciadas:
    - receptor: Recebe mensagens e tokens
    - gerenciador: Gerencia token e mensagens
    - interface_usuario: Interface com usuário
    Tratamento de erros:
    - Captura exceções gerais
    - Registra erros no log
    - Encerra programa graciosamente
    """
    try:
        logging.info(f"Iniciando nó {apelido} em {ip_local}:{porta_local}")
        # Inicia threads
        thread_receptor = threading.Thread(target=receptor)
        thread_gerenciador = threading.Thread(target=gerenciador)
        thread_interface = threading.Thread(target=interface_usuario)
        # Configura threads como daemon (encerram quando programa principal termina)
        thread_receptor.daemon = True
        thread_gerenciador.daemon = True
        thread_interface.daemon = True
        # Inicia execução das threads
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