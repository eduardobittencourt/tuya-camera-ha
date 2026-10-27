<p align="center">
  <img src="../custom_components/tuya_camera/brand/logo.png" alt="Tuya" width="220">
</p>

# Tuya Camera para Home Assistant

[![HACS padrão](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default/blob/master/integration)

Uma integração para conectar câmeras compatíveis do **Tuya Smart e Smart Life**
pelo próprio Home Assistant. Você faz login na interface do HA; a integração
busca as câmeras e executa os protocolos em Python dentro da integração.

**Estável 0.4.0:** os protocolos da câmera executam em Python dentro da
integração. O executável Go foi removido. Não é preciso habilitar versões beta
no HACS; veja a [arquitetura](architecture.md).

[English](../README.md) · [Instalação detalhada](installation.md) ·
[Compatibilidade](compatibility.md) · [Resolução de problemas](troubleshooting.md) ·
[Investigação 100% LAN](offline-operation.pt-BR.md)

[Validação da estável](validation-0.4.0.md) · [Validação da migração Python](validation-0.4.0b1.md) · [Validação da troca de domínio](validation-0.4.0b2.md)

## O que funciona

- Câmeras nativas no HA, vídeo com som e capturas de imagem novas.
- Reprodução por HLS e pelo WebRTC do Home Assistant.
- Descoberta de câmeras, reconfiguração e novo login quando a sessão expira.
- Sessões de mídia gerenciadas em Python, sem baixar um executável de protocolo.
- Vídeo H.264 sem reconversão e H.265 convertido para H.264 em 720p / 15 fps.
- [Controles e sensores LAN](local-controls.md)
  para modelos que aceitam o protocolo de controle local da Tuya.

Tudo é configurado pela interface. Não é necessário instalar outro add-on,
configurar ONVIF, copiar IDs ou editar YAML.

**Usamos APIs privadas da Tuya, que podem mudar.**
Compatibilidade depende do modelo e do firmware. A autenticação e a sinalização
precisam de internet; o vídeo pode usar conexão direta ou TURN. Não prometemos
funcionamento totalmente offline nem suporte a toda câmera Tuya.

PTZ, áudio bidirecional, MFA e captcha interativos
não estão implementados.

Os novos controles não usam fallback para a nuvem, mas precisam que o firmware
aceite conexões LAN. Na câmera Positivo a bateria testada, a sessão de mídia
abriu uma janela de telemetria LAN. A integração só habilita sensores e
ajustes após leituras válidas; entidades antigas sem confirmação são
desabilitadas, preservando os identificadores. Durante o repouso, as últimas
leituras continuam disponíveis com horário e indicação de conexão inativa.
Movimento e som ficam desabilitados por padrão em câmeras a bateria, pois não
recebem eventos continuamente durante o sono. O stream continua dependendo de
autenticação e sinalização Tuya pela internet.

## Instalação

Disponível no **catálogo padrão do HACS**, sem adicionar repositório personalizado.

A release estável [0.4.0](https://github.com/eduardobittencourt/tuya-camera-ha/releases/tag/v0.4.0) permite instalar sem habilitar versões beta.
Veja o [relatório da estável](validation-0.4.0.md). O runtime Python e o pacote
com domínio novo foram validados pelo HACS no HA Core 2026.10.4 antes da promoção;
os [resultados medidos](validation-0.4.0b2.md) incluem a preservação da conta e entidades.

É necessário ter **HA 2026.9 ou mais recente**, Linux, HACS e
FFmpeg. HA OS e Container já incluem FFmpeg. Em uma instalação Linux própria,
o FFmpeg precisa estar disponível com os codecs H.264 e AAC.

[![Abrir no HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=tuya-camera-ha&category=integration)

O novo nome/domínio vale a partir da **0.4.0b2**, incluindo a estável **0.4.0**.
Releases anteriores aparecem como **Tuya Camera Bridge**. Para trocar
uma instalação existente, siga o [procedimento de mudança de domínio](installation.md#updates-and-rediscovery).

1. Abra o **HACS** e procure **Tuya Camera**.
2. Baixe a release estável **0.4.0** e reinicie o HA.
3. Vá a **Configurações → Dispositivos e serviços → Adicionar integração** e
   procure **Tuya Camera**.
4. Escolha Tuya Smart ou Smart Life e informe a conta, a senha e o código de
   país usados no aplicativo. Para o Brasil, use `55`.
5. Abra a câmera e ative o som no player.

Uma release em rascunho não pode ser baixada publicamente. A versão 0.4 usa
dependências Python instaladas pelo HA, incluindo um commit oficial do aiortc
compatível com o PyAV 19. Não baixa executável Go. Instalação e verificações
de dependências precisam de acesso ao GitHub e aos índices Python.

Se a instalação usa `tuya_camera_bridge`, inclusive por repositório personalizado,
siga o [procedimento de mudança de domínio](installation.md#updates-and-rediscovery)
antes de trocar para a 0.4.0. A atualização comum pelo HACS vale dentro do mesmo domínio.

## Câmera testada

A **Positivo Casa Inteligente Smart Câmera Wi-Fi com Bateria (11188736)**,
com firmware **1.1.48**, foi testada pelo Tuya Smart no HA OS 2026.9.4.
Vídeo HEVC/1080p, som PCM, capturas de imagem, recuperação de sessão e reprodução
no celular funcionaram. O proprietário identificou o modelo por este
[anúncio do fabricante](https://www.positivocasainteligente.com.br/smart-camera-bateria-wifi-11188736/p).
Ainda não medimos autonomia da bateria nem ciclos longos de repouso e despertar.
A primeira captura após iniciar ou recarregar a integração pode exceder o limite
de dez segundos do HA. Abra o vídeo, aguarde a reprodução e tente novamente.
Os resultados e essa limitação estão no [relatório da versão estável](validation-0.3.1.md).

O teste contínuo de cinco minutos não comprova estabilidade durante dias nem
recuperação após toda falha de rede. Veja a [tabela de compatibilidade](compatibility.md)
e o [relatório dos testes](validation-0.3.0b1.md).

## Privacidade e ajuda

A senha serve somente para o login e não é salva. A sessão fica no armazenamento
privado do HA. Não publique tokens, backups, `.storage`, IDs de câmera, imagens
privadas ou logs brutos do bridge.

Para ajuda, use [SUPPORT.md](../SUPPORT.md). Para contribuir, veja
[CONTRIBUTING.md](../CONTRIBUTING.md). Relatos de outros modelos ajudam a ampliar
a compatibilidade.

Projeto independente da comunidade, sem vínculo ou endosso da Tuya ou do
Home Assistant. Os nomes e logos pertencem aos seus respectivos titulares.
