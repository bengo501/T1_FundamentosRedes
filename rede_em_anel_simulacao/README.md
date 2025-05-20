# Simulação de Rede em Anel

Este projeto implementa uma simulação de rede local em anel, utilizando o protocolo UDP para comunicação entre os nós. A rede é controlada por um token que circula entre as máquinas, permitindo a transmissão de mensagens de forma ordenada.

## Estrutura do Projeto

```
rede_em_anel_simulacao/
├── Bob/
│   ├── config.txt      # Configuração do nó Bob (gerador de token)
│   └── main.py         # Código fonte
├── Mary/
│   ├── config.txt      # Configuração do nó Mary
│   └── main.py         # Código fonte
└── John/
    ├── config.txt      # Configuração do nó John
    └── main.py         # Código fonte
```

## Requisitos

- Python 3.6 ou superior
- Módulos Python:
  - socket
  - threading
  - time
  - random
  - zlib
  - datetime

## Como Testar

### 1. Preparação

1. Abra três terminais diferentes
2. Em cada terminal, navegue até a pasta do projeto:
```bash
cd rede_em_anel_simulacao
```

### 2. Iniciando os Nós

Em cada terminal, execute um dos nós:

Terminal 1 (Bob - Gerador de Token):
```bash
cd Bob
python main.py
```

Terminal 2 (Mary):
```bash
cd Mary
python main.py
```

Terminal 3 (John):
```bash
cd John
python main.py
```

### 3. Testando Funcionalidades

#### 3.1 Envio de Mensagens Unicast

1. No terminal do Bob, escolha a opção 1
2. Digite o destino (ex: "Mary")
3. Digite a mensagem
4. Observe:
   - A mensagem aparecendo na fila
   - O token circulando
   - A mensagem sendo recebida por Mary
   - O ACK retornando para Bob

#### 3.2 Envio de Mensagens Broadcast

1. No terminal do Bob, escolha a opção 1
2. Digite o destino "TODOS"
3. Digite a mensagem
4. Observe:
   - A mensagem sendo recebida por todas as máquinas
   - O status "naoexiste" sendo mantido

#### 3.3 Testando Detecção de Erros

1. Envie várias mensagens entre os nós
2. Observe:
   - Mensagens com erro de CRC sendo detectadas
   - NACK sendo enviado
   - Retransmissão da mensagem
   - ACK após recebimento correto

#### 3.4 Testando Timeout do Token

1. Feche um dos terminais (simulando falha)
2. Observe:
   - O token sendo regenerado após timeout
   - Mensagens sendo marcadas como "naoexiste"

#### 3.5 Visualizando a Fila

1. Em qualquer terminal, escolha a opção 2
2. Observe:
   - Mensagens pendentes
   - Status de retransmissão
   - Limite de 10 mensagens

### 4. Verificando Funcionalidades

#### 4.1 Token
- Deve circular entre os nós
- Apenas Bob gera o token inicial
- Token é regenerado após timeout
- Alerta quando múltiplos tokens são detectados

#### 4.2 Mensagens
- Formato correto: "7777:controle;origem;destino;crc;mensagem"
- CRC32 para detecção de erros
- Retransmissão após NACK
- Remoção após ACK/naoexiste

#### 4.3 Fila
- Máximo de 10 mensagens
- Ordem FIFO (First In, First Out)
- Mensagens não são removidas até confirmação

#### 4.4 Logs
- Timestamp em todas as mensagens
- Status do token
- Eventos de rede
- Erros e retransmissões

### 5. Testes de Estresse

1. Envie muitas mensagens rapidamente
2. Feche e reabra terminais
3. Envie mensagens longas
4. Teste com diferentes tempos de token

### 6. Solução de Problemas

#### 6.1 Token não circula
- Verifique se todos os nós estão rodando
- Confirme as configurações de IP e porta
- Verifique se o Bob está gerando o token

#### 6.2 Mensagens não chegam
- Verifique o formato das mensagens
- Confirme se o token está circulando
- Verifique os logs de erro

#### 6.3 Erros de CRC frequentes
- Ajuste a probabilidade de erro no código
- Verifique a integridade das mensagens
- Monitore os logs de NACK

## Observações

- O projeto usa localhost (127.0.0.1) para testes
- As portas são: Bob (6000), Mary (6001), John (6002)
- O tempo do token é configurável no arquivo config.txt
- A probabilidade de erro é de 20% por padrão

## Limitações

- Testado apenas em ambiente local
- Não implementa recuperação de falhas complexas
- Interface básica via terminal
- Sem persistência de mensagens

## Contribuição

Para melhorar o projeto, considere:
1. Adicionar interface gráfica
2. Implementar mais testes
3. Adicionar estatísticas de rede
4. Melhorar tratamento de erros
5. Adicionar configuração via arquivo 