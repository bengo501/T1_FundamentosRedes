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

class Token:
    def __init__(self):
        self.sequencia = 0
        self.timestamp = time.time()
        self.node_id = None  # ID do nó que gerou o token
    
    def incrementar(self):
        self.sequencia += 1
        self.timestamp = time.time()
        logging.debug(f"[Token] 🔄 Token incrementado - Nova sequência: {self.sequencia}")
        logging.debug(f"[Token] ⏱️ Novo timestamp: {datetime.fromtimestamp(self.timestamp)}")
    
    def to_string(self):
        token_str = f"9000:{self.sequencia}:{self.timestamp}:{self.node_id}"
        logging.debug(f"[Token] 📝 Token convertido para string: {token_str}")
        return token_str
    
    @staticmethod
    def from_string(token_str):
        if ":" in token_str:
            try:
                _, seq, ts, node_id = token_str.split(":")
                logging.debug(f"[Token] 🔍 Decodificando token: seq={seq}, ts={ts}, node={node_id}")
                return int(seq), float(ts), node_id
            except ValueError as e:
                logging.error(f"[Token] ❌ Erro ao decodificar token: {token_str}")
                logging.error(f"[Token] ❌ Erro específico: {str(e)}")
                return 0, 0, None
        return 0, 0, None

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
        logging.FileHandler(f"logs_Computer2.log", mode='w', encoding="utf-8")
    ]
)

# Configurações globais do sistema
fila_mensagens = []  # Lista de tuplas: (destino, mensagem, reenviado?, tentativas)
token_presente = False
ultima_passagem_token = time.time()
tempo_maximo_token = 5  # Tempo máximo para o token voltar (em segundos)
tempo_minimo_token = 0.5  # Tempo mínimo entre tokens (em segundos)
nos_ativos = set()  # Conjunto de nós ativos na rede
MAX_TENTATIVAS = 2  # Número máximo de tentativas de envio

# Estados do token
ESTADO_TOKEN = {
    'CIRCULANDO': '🔄 Token em circulação',
    'EM_USO': '📤 Token em uso (enviando mensagem)',
    'PERDIDO': '⚠️ Token perdido',
    'MULTIPLO': '⚠️ Múltiplos tokens detectados',
    'REGENERADO': '🔄 Token regenerado'
}

# Estados de mensagem
ESTADO_MENSAGEM = {
    'ENVIANDO': '📤 Enviando mensagem',
    'ERRO_CRC': '⚠️ Erro de CRC detectado',
    'RETRANSMITINDO': '🔄 Retransmitindo mensagem',
    'DESCARTADA': '❌ Mensagem descartada',
    'ENTREGUE': '✅ Mensagem entregue',
    'NAO_EXISTE': '❓ Destino não existe'
}

# Controle de tempo do token
class ControleToken:
    def __init__(self):
        self.ultima_passagem = time.time()
        self.ultimo_token_time = time.time()
        self.contador_tokens = 0
        self.token_gerado = False
        self.tempo_maximo = 15  # Aumentado para 15 segundos
        self.tempo_minimo = 0.5
        self.ultima_sequencia = 0
        self.token = Token()
        self.token.node_id = apelido  # Identificador do nó
        self.regenerando = False
        self.tokens_recebidos = {}  # Dicionário para rastrear tokens com timestamp
        self.tempo_limpeza = 30  # Tempo para limpar tokens antigos
        self.max_tokens_armazenados = 100  # Limite de tokens armazenados
        self.contador_timeouts = 0
        self.contador_duplicados = 0
        logging.debug(f"[Token] 🆕 Controle de token inicializado para {apelido}")

    def verificar_timeout(self):
        if self.regenerando:
            return False
            
        tempo_atual = time.time()
        tempo_passado = tempo_atual - self.ultima_passagem
        
        # Log detalhado do estado do token
        logging.debug(f"[Token] ⏱️ Tempo desde último token: {tempo_passado:.2f}s")
        logging.debug(f"[Token] 🔄 Estado atual: {'Regenerando' if self.regenerando else 'Normal'}")
        
        if tempo_passado > self.tempo_maximo:
            self.regenerando = True
            self.contador_timeouts += 1
            logging.warning(f"[Token] ⚠️ TIMEOUT DO TOKEN!")
            logging.warning(f"[Token] ⏱️ Token não retornou em {tempo_passado:.2f} segundos")
            logging.warning(f"[Token] 📊 Total de timeouts: {self.contador_timeouts}")
            return True
        return False

    def regenerar_token(self):
        if not self.regenerando:
            return None
            
        self.token.incrementar()
        self.ultima_sequencia = self.token.sequencia
        self.regenerando = False
        self.atualizar_tempo()
        logging.info(f"[Token] 🔄 Token regenerado - Nova sequência: {self.token.sequencia}")
        logging.debug(f"[Token] 📊 Estado após regeneração:")
        logging.debug(f"[Token] 🔢 Sequência: {self.token.sequencia}")
        logging.debug(f"[Token] ⏱️ Timestamp: {datetime.fromtimestamp(self.token.timestamp)}")
        logging.debug(f"[Token] 🏷️ Node ID: {self.token.node_id}")
        return self.token.to_string()

    def verificar_tempo_minimo(self):
        tempo_atual = time.time()
        tempo_passado = tempo_atual - self.ultimo_token_time
        
        # Limpa tokens antigos
        self._limpar_tokens_antigos()
        
        if tempo_passado < self.tempo_minimo:
            logging.warning(f"[Token] ⚠️ ALERTA: TOKEN MUITO RÁPIDO!")
            logging.warning(f"[Token] ⏱️ Token recebido em {tempo_passado:.2f} segundos")
            return True
        return False

    def _limpar_tokens_antigos(self):
        tempo_atual = time.time()
        tokens_para_remover = []
        
        # Remove tokens antigos
        for seq, (timestamp, _) in self.tokens_recebidos.items():
            if tempo_atual - timestamp > self.tempo_limpeza:
                tokens_para_remover.append(seq)
        
        for seq in tokens_para_remover:
            del self.tokens_recebidos[seq]
            
        # Se ainda houver muitos tokens, remove os mais antigos
        if len(self.tokens_recebidos) > self.max_tokens_armazenados:
            tokens_ordenados = sorted(self.tokens_recebidos.items(), key=lambda x: x[1][0])
            for seq, _ in tokens_ordenados[:len(tokens_ordenados) - self.max_tokens_armazenados]:
                del self.tokens_recebidos[seq]

    def processar_token(self, token_str):
        sequencia, timestamp, node_id = Token.from_string(token_str)
        
        # Log detalhado do processamento
        logging.debug(f"[Token] 🔍 Processando token:")
        logging.debug(f"[Token] 📊 Sequência atual: {self.token.sequencia}")
        logging.debug(f"[Token] 📊 Sequência recebida: {sequencia}")
        logging.debug(f"[Token] 📊 Node ID atual: {self.token.node_id}")
        logging.debug(f"[Token] 📊 Node ID recebido: {node_id}")
        
        # Verifica se é um token duplicado
        if sequencia in self.tokens_recebidos:
            self.contador_duplicados += 1
            logging.warning(f"[Token] ⚠️ Token duplicado detectado!")
            logging.warning(f"[Token] 📊 Sequência: {sequencia}")
            logging.warning(f"[Token] 📊 Total de duplicados: {self.contador_duplicados}")
            logging.warning(f"[Token] 🔍 Token anterior recebido em: {datetime.fromtimestamp(self.tokens_recebidos[sequencia][0])}")
            return False
        
        # Atualiza o token local com os dados recebidos
        self.token.sequencia = sequencia
        self.token.timestamp = timestamp
        self.token.node_id = node_id
        
        # Incrementa a sequência para o próximo nó
        self.token.incrementar()
        
        # Armazena o token com timestamp e node_id
        self.tokens_recebidos[sequencia] = (timestamp, node_id)
        logging.debug(f"[Token] ✅ Token processado e incrementado")
        return True

    def atualizar_tempo(self):
        self.ultima_passagem = time.time()
        self.ultimo_token_time = time.time()
        self.contador_tokens += 1
        logging.debug(f"[Token] ⏱️ Tempo atualizado - Total de tokens: {self.contador_tokens}")

    def mostrar_status(self):
        tempo_atual = time.time()
        tempo_desde_ultimo = tempo_atual - self.ultima_passagem
        logging.info(f"[Token] 📊 Status do Token:")
        logging.info(f"[Token] ⏱️ Tempo desde último token: {tempo_desde_ultimo:.2f}s")
        logging.info(f"[Token] 🔢 Tokens recebidos: {self.contador_tokens}")
        logging.info(f"[Token] 🔄 Sequência atual: {self.token.sequencia}")
        logging.info(f"[Token] ⚠️ Total de timeouts: {self.contador_timeouts}")
        logging.info(f"[Token] ⚠️ Total de duplicados: {self.contador_duplicados}")
        logging.info(f"[Token] 📝 Tokens em memória: {len(self.tokens_recebidos)}")

# Instância do controle de token
controle_token = ControleToken()

# Configuração de rede
ip_local = "127.0.0.1"  # Usando localhost para teste
porta_local = 6001  # Porta fixa para o Computador2

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

def registrar_log(mensagem: str, mostrar_terminal: bool = False):
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
    # Verifica se o nó já está mapeado com os mesmos dados
    if apelido in mapeamento_apelidos:
        ip_atual, porta_atual = mapeamento_apelidos[apelido]
        if ip_atual == ip and porta_atual == porta:
            return  # Nó já está mapeado corretamente, não precisa atualizar
    
    mapeamento_apelidos[apelido] = (ip, porta)
    nos_ativos.add(apelido)
    mensagem = f"Nó {apelido} adicionado ao mapeamento: {ip}:{porta}"
    registrar_log(f"[{apelido}] {mensagem}")
    
    # Envia mensagem de atualização para todos os nós ativos
    mensagem_atualizacao = f"UPDATE:{apelido}:{ip}:{porta}"
    for no in nos_ativos:
        if no != apelido:  # Não envia para o próprio nó
            enviar_udp(*mapeamento_apelidos[no], mensagem_atualizacao)
            logging.info(f"[{apelido}] Enviando atualização para {no}")

def enviar_lista_nos(destino: str):
    """
    Envia a lista completa de nós ativos para um destino específico
    Args:
        destino: Nome do nó de destino
    """
    if destino in mapeamento_apelidos:
        for no in nos_ativos:
            if no != destino:  # Não envia o próprio nó
                ip, porta = mapeamento_apelidos[no]
                mensagem = f"UPDATE:{no}:{ip}:{porta}"
                enviar_udp(*mapeamento_apelidos[destino], mensagem)
                logging.info(f"[{apelido}] Enviando informação do nó {no} para {destino}")

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
    logging.info(f"[{apelido}] Status da rede: {len(nos_ativos)} nós ativos")

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

def verificar_destino_ativo(destino: str) -> bool:
    """
    Verifica se o destino está ativo na rede
    """
    return destino in nos_ativos or destino == "TODOS"

def processar_resposta_mensagem(controle: str, destino: str, texto: str):
    """
    Processa a resposta de uma mensagem enviada
    """
    with mutex:
        if not fila_mensagens:
            return

        destino_atual, texto_atual, reenviado, tentativas = fila_mensagens[0]
        
        if controle == "ACK":
            mostrar_estado_mensagem('ENTREGUE', f"Mensagem entregue com sucesso para {destino}")
            logging.info(f"[{apelido}] Mensagem entregue com sucesso para {destino}")
            fila_mensagens.pop(0)
        elif controle == "NACK":
            if tentativas < MAX_TENTATIVAS:
                mostrar_estado_mensagem('RETRANSMITINDO', f"Retransmitindo mensagem (tentativa {tentativas + 1})")
                logging.warning(f"[{apelido}] Erro de CRC detectado. Retransmitindo...")
                fila_mensagens[0] = (destino_atual, texto_atual, True, tentativas + 1)
            else:
                mostrar_estado_mensagem('DESCARTADA', "Máximo de tentativas atingido")
                logging.error(f"[{apelido}] Mensagem descartada após {MAX_TENTATIVAS} tentativas")
                fila_mensagens.pop(0)
        elif controle == "naoexiste":
            mostrar_estado_mensagem('NAO_EXISTE', f"Destino {destino} não existe na rede")
            logging.warning(f"[{apelido}] Destino {destino} não existe na rede")
            fila_mensagens.pop(0)

def mostrar_estado_token(estado, detalhes=""):
    """
    Mostra o estado atual do token com timestamp
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensagem = f"{ESTADO_TOKEN[estado]}"
    if detalhes:
        mensagem += f" - {detalhes}"
    logging.info(f"[Token] {mensagem}")

def mostrar_estado_mensagem(estado: str, detalhes: str = ""):
    """
    Mostra o estado atual da mensagem com timestamp
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensagem = f"{ESTADO_MENSAGEM[estado]}"
    if detalhes:
        mensagem += f" - {detalhes}"
    logging.info(f"[Mensagem] {mensagem}")

def enviar_mensagem_usuario():
    print("\nDestino (apelido ou TODOS): ", end="")
    destino = input().strip()
    
    # Valida se o destino existe
    if destino != "TODOS" and not verificar_destino_ativo(destino):
        print(f"\nErro: Destino '{destino}' não existe na rede!")
        print("Destinos disponíveis:", ", ".join(sorted(nos_ativos)))
        input("\nPressione Enter para continuar...")
        return
    
    print("Mensagem: ", end="")
    mensagem = input().strip()
    
    if len(fila_mensagens) >= 10:
        print("\nErro: Fila cheia! Máximo de 10 mensagens atingido.")
        input("\nPressione Enter para continuar...")
        return
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensagem_completa = f"{timestamp} | {apelido} -> {destino}: {mensagem}"
    with mutex:
        fila_mensagens.append((destino, mensagem_completa, False, 0))
        logging.info(f"[Fila] Mensagem adicionada: {mensagem_completa}")
        print(f"\nMensagem adicionada à fila.")
        input("\nPressione Enter para continuar...")

def ver_fila():
    print("\n" + "="*50)
    print("FILA DE MENSAGENS".center(50))
    print("="*50)
    if not fila_mensagens:
        print("\nFila vazia")
    else:
        print("\nMensagens pendentes:")
        for i, (dest, msg, reenv, tentativas) in enumerate(fila_mensagens, 1):
            print(f"{i}. Para: {dest} | Mensagem: {msg} | Reenviado: {reenv} | Tentativas: {tentativas}")
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

def processar_token(mensagem):
    """
    Processa o token recebido e retorna informações sobre sua origem e destino
    """
    try:
        _, seq, ts, node_id = mensagem.split(":")
        return {
            'sequencia': int(seq),
            'timestamp': float(ts),
            'origem': node_id,
            'destino': apelido
        }
    except Exception as e:
        logging.error(f"[Token] ❌ Erro ao processar token: {e}")
        return None

# ================================
# THREAD DE RECEPÇÃO
# ================================
def receptor():
    """
    Thread responsável por receber mensagens e tokens
    Gerencia a chegada de tokens e pacotes de dados
    """
    global token_presente, fila_mensagens
    socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_udp.bind((ip_local, porta_local))
    mostrar_estado_token('CIRCULANDO', f"Receptor ativo em {ip_local}:{porta_local}")
    logging.info(f"[{apelido}] Receptor ativo em {ip_local}:{porta_local}")
    logging.info(f"[{apelido}] Aguardando mensagens e tokens...")
    logging.info(f"[{apelido}] Próximo nó: {ip_destino}:{porta_destino}")

    # Adiciona o próprio nó ao mapeamento
    atualizar_mapeamento(apelido, ip_local, porta_local)

    # Envia mensagem de descoberta para o próximo nó
    mensagem_descoberta = f"DISCOVER:{apelido}:{ip_local}:{porta_local}"
    enviar_udp(ip_destino, porta_destino, mensagem_descoberta)
    logging.info(f"[{apelido}] Enviando mensagem de descoberta para {ip_destino}:{porta_destino}")

    while True:
        try:
            dados, endereco = socket_udp.recvfrom(2048)
            mensagem = dados.decode()

            if mensagem.startswith("DISCOVER:"):  # Mensagem de descoberta
                _, nome, ip, porta = mensagem.split(":")
                porta = int(porta)
                if nome != apelido:  # Ignora mensagens próprias
                    atualizar_mapeamento(nome, ip, porta)
                    logging.info(f"[{apelido}] Nó descoberto: {nome} ({ip}:{porta})")
                    # Envia lista completa de nós para o novo nó
                    enviar_lista_nos(nome)
                    # Repassa a mensagem de descoberta
                    enviar_udp(ip_destino, porta_destino, mensagem)

            elif mensagem.startswith("UPDATE:"):  # Mensagem de atualização
                _, nome, ip, porta = mensagem.split(":")
                porta = int(porta)
                if nome != apelido:  # Ignora mensagens próprias
                    atualizar_mapeamento(nome, ip, porta)
                    logging.info(f"[{apelido}] Mapeamento atualizado: {nome} ({ip}:{porta})")
                    # Repassa a atualização
                    enviar_udp(ip_destino, porta_destino, mensagem)

            elif mensagem.startswith("9000:"):  # Token com sequência
                with lock_token:
                    # Verifica tempo mínimo entre tokens
                    if controle_token.verificar_tempo_minimo():
                        continue
                    
                    # Processa o token
                    token_info = processar_token(mensagem)
                    if token_info:
                        logging.info(f"[Token] 📨 Token recebido de {token_info['origem']} para {token_info['destino']}")
                        logging.info(f"[Token] 🔢 Sequência: {token_info['sequencia']}")
                        logging.info(f"[Token] ⏱️ Timestamp: {datetime.fromtimestamp(token_info['timestamp'])}")
                        logging.debug(f"[Token] 🔍 Estado do token após processamento:")
                        logging.debug(f"[Token] 📊 Sequência atual: {controle_token.token.sequencia}")
                        logging.debug(f"[Token] ⏱️ Timestamp atual: {datetime.fromtimestamp(controle_token.token.timestamp)}")
                        logging.debug(f"[Token] 🏷️ Node ID atual: {controle_token.token.node_id}")
                    
                    if not controle_token.processar_token(mensagem):
                        continue
                    
                    # Atualiza controle de tempo
                    controle_token.atualizar_tempo()
                    token_presente = True
                    mostrar_estado_token('CIRCULANDO', f"Token recebido - Pronto para enviar mensagens")
                    logging.info(f"[{apelido}] ✅ Token recebido - Pronto para enviar mensagens")

            elif mensagem.startswith("7777:"):  # Pacote de dados
                _, conteudo = mensagem.split(":", 1)
                controle, origem, destino, crc, texto = conteudo.split(";", 4)

                # Atualiza mapeamento com o nó de origem
                if origem not in mapeamento_apelidos:
                    atualizar_mapeamento(origem, endereco[0], endereco[1])

                # Ignora mensagens próprias
                if origem == apelido:
                    if controle == "naoexiste":
                        logging.info(f"[{apelido}] Ignorando mensagem própria: {texto}")
                        continue
                    else:
                        print("\n" + "="*50)
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] RETORNO DE MENSAGEM:")
                        print(f"Status: {controle}")
                        print(f"Mensagem: {texto}")
                        print("="*50 + "\n")
                        logging.info(f"[{apelido}] Pacote retornou: {controle}")
                        processar_resposta_mensagem(controle, destino, texto)
                        # Após processar a resposta, passa o token
                        token_str = controle_token.token.to_string()
                        enviar_udp(ip_destino, porta_destino, token_str)
                        token_presente = False
                        controle_token.atualizar_tempo()
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
                        logging.info(f"[{apelido}] MENSAGEM RECEBIDA de {origem}: {texto}")
                        resposta = f"7777:ACK;{origem};{apelido};{crc};{texto}"
                    else:
                        print("\n" + "="*50)
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ERRO DE CRC:")
                        print(f"De: {origem}")
                        print(f"Para: {destino}")
                        print(f"Conteúdo: {texto}")
                        print(f"Status: CRC INVÁLIDO")
                        print("="*50 + "\n")
                        logging.info(f"[{apelido}] Erro de CRC! Enviando NACK para {origem}")
                        resposta = f"7777:NACK;{origem};{apelido};{crc};{texto}"
                    enviar_udp(*mapeamento_apelidos[origem], resposta)

                else:
                    logging.info(f"[{apelido}] Repassando mensagem para {ip_destino}:{porta_destino}")
                    enviar_udp(ip_destino, porta_destino, mensagem)

        except Exception as erro:
            logging.error(f"[ERRO] Falha na recepção: {erro}")

# ================================
# THREAD DO GERENCIADOR
# ================================
def gerenciador():
    """
    Thread responsável por gerenciar o token e enviar mensagens
    Controla o fluxo de dados na rede em anel
    """
    global token_presente, fila_mensagens
    
    # Se for o gerador inicial, envia o primeiro token
    if gerar_token:
        time.sleep(2)  # Aguarda a rede estabilizar
        mostrar_estado_token('CIRCULANDO', "Iniciando circulação do token...")
        logging.info(f"[{apelido}] Iniciando circulação do token...")
        token_str = controle_token.token.to_string()
        logging.info(f"[Token] 📤 Enviando token de {apelido} para {ip_destino}:{porta_destino}")
        enviar_udp(ip_destino, porta_destino, token_str)
        controle_token.atualizar_tempo()
        controle_token.token_gerado = True
    
    while True:
        try:
            with mutex:
                # Verifica timeout do token
                if gerar_token and controle_token.verificar_timeout():
                    mostrar_estado_token('PERDIDO', f"Token não retornou em {controle_token.tempo_maximo}s")
                    logging.warning(f"[{apelido}] ⚠️ TIMEOUT! Regenerando token...")
                    logging.warning(f"[{apelido}] Última passagem do token: {time.time() - controle_token.ultima_passagem:.2f}s atrás")
                    token_str = controle_token.regenerar_token()
                    if token_str:
                        logging.info(f"[Token] 📤 Regenerando token de {apelido} para {ip_destino}:{porta_destino}")
                        enviar_udp(ip_destino, porta_destino, token_str)
                        controle_token.atualizar_tempo()
                        mostrar_estado_token('REGENERADO', "Novo token enviado")
                    continue

                # Se tem token, processa mensagens
                if token_presente:
                    if fila_mensagens:
                        destino, texto, reenviado, tentativas = fila_mensagens[0]
                        
                        # Verifica se o destino está ativo
                        if not verificar_destino_ativo(destino):
                            mostrar_estado_mensagem('NAO_EXISTE', f"Destino {destino} não existe na rede")
                            logging.warning(f"[{apelido}] Destino {destino} não existe na rede")
                            fila_mensagens.pop(0)
                            continue
                        
                        mostrar_estado_token('EM_USO', "Processando mensagem da fila")
                        
                        # Prepara a mensagem
                        if reenviado:
                            controle = "naoexiste"
                            mensagem_pronta = texto
                        else:
                            controle = "naoexiste"
                            mensagem_pronta = inserir_erro(texto)
                        
                        # Envia mensagem
                        crc = calcular_crc(mensagem_pronta)
                        pacote = f"7777:{controle};{apelido};{destino};{crc};{mensagem_pronta}"
                        logging.info(f"[{apelido}] Enviando mensagem para {destino}")
                        enviar_udp(ip_destino, porta_destino, pacote)
                        logging.info(f"[{apelido}] Mensagem enviada: {mensagem_pronta}")
                        
                        # Aguarda um tempo para a mensagem voltar
                        time.sleep(tempo_token)
                    else:
                        # Se não tem mensagem, passa o token
                        token_str = controle_token.token.to_string()
                        mostrar_estado_token('CIRCULANDO', "Nenhuma mensagem. Passando token.")
                        logging.info(f"[Token] 📤 Enviando token de {apelido} para {ip_destino}:{porta_destino}")
                        enviar_udp(ip_destino, porta_destino, token_str)
                        token_presente = False
                        controle_token.atualizar_tempo()

            # Mostra status do token a cada segundo
            if gerar_token and time.time() - controle_token.ultima_passagem > 1:
                controle_token.mostrar_status()
            
            time.sleep(0.1)  # Pequena pausa para não sobrecarregar a CPU
        except Exception as erro:
            logging.error(f"[ERRO] Falha no gerenciador: {erro}")

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