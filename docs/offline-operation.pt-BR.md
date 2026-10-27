# Operação 100% LAN: conclusão da investigação

Revisão final: **27 de outubro de 2026 UTC**. [English](offline-operation.md).

**A migração para Python terminou; a operação diária sem nuvem ainda não foi
comprovada.** Conseguimos acordar a câmera por um servidor local e obter vídeo
novo pela LAN. O que falta é repetir o ciclo completo de repouso e wake com a
WAN bloqueada. Por isso, o servidor experimental não será incorporado como uma
funcionalidade 100% LAN neste momento. Os ensaios não provam impossibilidade.

A conclusão vale para **uma Positivo Casa Inteligente Smart Câmera Wi-Fi com
Bateria, SKU 11188736, firmware 1.1.48**, protocolo LAN 3.3 e low-power v1.
Outros modelos e firmwares podem se comportar de outra forma.

## Como chegamos à conclusão

| Etapa | O que observamos | O que isso permite concluir |
| --- | --- | --- |
| Procurar um wake direto | Discovery, Wake-on-LAN e sondagens UDP não abriram a porta local | Essas sondagens não encontraram um listener; não descartam todo mecanismo proprietário |
| Identificar o caminho real | A câmera inicia uma conexão TCP autenticada de baixo consumo; verificamos autenticação, heartbeats e wake de nove bytes | O wake pode vir de um servidor local usando o protocolo correto |
| Acordar e abrir vídeo | Wake com IPv4 WAN bloqueado abriu TCP 6668; sessões novas decodificaram 640×360 pela LAN | Um ciclo local funciona após preparação online |
| Repetir sem WAN | Uma política de FIN após 2,501 s não produziu segunda autenticação em 180 s | Esse ensaio não resolveu a volta ao repouso; RST isolado não significa falha |
| Comparar com acesso externo | Com WAN disponível, dois wakes locais funcionaram. Liberando somente TCP 8883, houve três autenticações locais, dois wakes e vídeo novo | O serviço TLS externo é um forte candidato na transição pós-wake; não sabemos quais mensagens são necessárias nem se é a única dependência |
| Substituir o serviço TLS | Certificado autoassinado foi rejeitado; certificado público válido para domínio próprio também | Apenas redirecionar o tráfego para um broker local não bastou |
| Separar nome e confiança | Oito conexões controladas: SAN correto retornou `UNKNOWN_CA`; SAN incorreto, `BAD_CERTIFICATE`, independentemente do CN | Há forte evidência de validação do nome do serviço e uma barreira de confiança; não provamos pinning nem enumeramos as CAs aceitas |
| Conferir as alternativas | Consulta atual confirmou DP149 `wireless_awake`, booleano gravável | Existe uma hipótese concreta de transição nativa ainda não validada offline |

A identidade solicitada continuou sendo `m2.tuyaus.com` mesmo com desvio de IP.
Um certificado de domínio próprio tem outra identidade. Nenhuma conexão TLS da
câmera foi aceita pelo substituto; portanto, a emulação MQTT e os ciclos
condicionados a esse sucesso não chegaram a ser testados.

## A ressalva do DP 149

A última etapa foi somente de leitura. As APIs de consulta da conta confirmaram
firmware 1.1.48 e **21 definições de DPs**, iguais ao schema já guardado no HA.
O DP149 é `wireless_awake`, booleano, `rw`. Isso descreve uma capacidade anunciada,
não comprova efeito nem transporte no firmware. Não escrevemos DPs nessa revisão.

O [SDK Android](https://developer.tuya.com/en/docs/app-development/doorbell?id=Ka6nxw2gncv8t)
apresenta esse DP como estado de wake. O
[guia de firmware 4.x](https://developer.tuya.com/en/docs/iot-device-dev/sdk?id=K95019g5w3eiq)
também menciona controle de repouso, mas suas descrições de polaridade são
inconsistentes e a sequência inclui comunicação com servidor. A referência é a
seção **Doorbell feature → Devices enter sleep mode**, revisada pela Tuya em
26/06/2024; o parâmetro `id=K95019g5w3eiq` identifica o documento na URL.
Uma função interna
do firmware não é automaticamente um comando LAN disponível ao usuário.

As antigas tentativas UDP não substituem um teste autenticado por TCP enquanto
a câmera está acordada. Portanto, **não descartamos o DP149 como alternativa**.
O DP147 `wireless_lowpower`, por sua vez, é limiar de alerta de bateria baixa,
conforme o [guia de bateria](https://developer.tuya.com/en/docs/app-development/low-power-doorbell?id=Kad3pl13guhil),
e não uma opção para desligar a dependência externa.

Também não encontramos uma configuração suportada de broker, CA ou modo offline
nos materiais examinados. O escopo foi código do cliente Python, documentação
pública dos SDKs, página do fabricante e schema atual. Não houve decompilação do
app instalado nem análise de imagem binária do firmware. Isso limita a conclusão:
não encontrar uma opção nessas fontes não prova que ela inexista.

## Por que encerrar esta rodada aqui

O obstáculo atual é a volta ao canal de baixo consumo sem o serviço externo,
e não gerar os bytes de wake ou receber vídeo. A substituição testada parou no
TLS; a alternativa DP149 continua sem validação. Além disso, os desvios de rede
usados em laboratório exigem controle do roteador/AP e não são uma instalação
pela interface do HA.

A integração **0.4.0 já é Python**, mas continua usando wake pela nuvem quando
a porta local da câmera está fechada. Os protótipos Go citados nos testes antigos
são históricos. Não houve mudança no produto nesta etapa documental.

## O que mudaria a conclusão

Vale reabrir a investigação com uma configuração suportada e aplicável a este
modelo para endpoint/confiança/modo offline; uma semântica e comando DP149
confirmados que permitam voltar ao repouso sem TCP8883; ou uma reprodução de
ciclos realmente isolados. Para o DP149, o próximo experimento deve observar o
comando normal, confirmar significado/polaridade e só então comparar uma escrita
LAN autenticada, com recuperação disponível.

Antes de anunciar operação diária offline, precisamos bloquear IPv4 e IPv6 da
câmera e do cliente, verificar o bloqueio também para conexões existentes usando
contadores ou captura de tráfego no upstream, controlar DNS e caminhos
alternativos e distinguir tráfego local dos fallbacks de nuvem/TURN. Precisamos
repetir ciclos com mídia nova, telemetria e mudanças de ajuste confirmadas.
Repouso longo, reinício do HA, ciclo de energia da câmera e persistência e
recuperação das credenciais também precisam passar. Eventos e autonomia de
bateria exigem medições próprias.

Os ensaios atuais tiveram preparação online; o isolamento posterior foi IPv4,
com DNS LAN disponível. Porta fechada e autenticação low-power são indicadores
observáveis, não medições elétricas de sono. Capturas incompletas, janelas de
tempo limitadas e uma falha corrigida no relay impedem conclusões universais.
Recuperação online posterior é controle de funcionamento, não evidência offline.

## Onde conferir as evidências

O [guia técnico em inglês](offline-operation.md) reúne critérios e referências.
O [relatório cronológico](local-wake-investigation.md) detalha método, controles,
resultados negativos, limitações e restauração de cada ensaio.
As [evidências sanitizadas](evidence/local-wake/README.md) incluem o schema público
consultado e os eventos TLS da matriz, sem chaves, IDs de dispositivo ou capturas
privadas. O leitor consegue acompanhar e contestar o raciocínio; não publicamos
um pacote executável de reprodução nem as capturas necessárias para uma
verificação independente de cada pacote de rede.
