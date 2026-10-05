<p align="center">
  <img src="../custom_components/tuya_camera_bridge/brand/logo.png" alt="Tuya" width="220">
</p>

# Tuya Camera Bridge para Home Assistant

Uma integração para conectar câmeras compatíveis do **Tuya Smart e Smart Life**
pelo próprio Home Assistant. Você faz login na interface do HA; a integração
busca as câmeras e instala e gerencia o bridge de vídeo automaticamente.

[English](../README.md) · [Instalação detalhada](installation.md) ·
[Compatibilidade](compatibility.md) · [Resolução de problemas](troubleshooting.md)

## O que funciona

- Câmeras nativas no HA, vídeo com som e capturas de imagem novas.
- Reprodução por HLS e pelo WebRTC do Home Assistant.
- Descoberta de câmeras, reconfiguração e novo login quando a sessão expira.
- Reinício automático do bridge após uma falha.
- Vídeo H.264 sem reconversão e H.265 convertido para H.264 em 720p / 15 fps.

Tudo é configurado pela interface. Não é necessário instalar outro add-on,
configurar ONVIF, copiar IDs ou editar YAML.

**Usamos APIs privadas da Tuya, que podem mudar.**
Compatibilidade depende do modelo e do firmware. A autenticação e a sinalização
precisam de internet; o vídeo pode usar conexão direta ou TURN. Não prometemos
funcionamento totalmente offline nem suporte a toda câmera Tuya.

PTZ, áudio bidirecional, configurações da câmera, MFA e captcha interativos
não estão implementados.

## Instalação

A release estável [0.3.1](https://github.com/eduardobittencourt/tuya-camera-ha/releases/tag/v0.3.1) permite instalar sem habilitar versões beta.
A instalação pelo HACS e o download automático do bridge foram validados no
HA OS 2026.9.4, preservando a conta e a câmera da instalação anterior. Veja a
[validação da release estável](validation-0.3.1.md).

É necessário ter **HA 2026.9 ou mais recente**, Linux **amd64 ou ARM64**, HACS e
FFmpeg. HA OS e Container já incluem FFmpeg. Em uma instalação Linux própria,
o FFmpeg precisa estar disponível com os codecs H.264 e AAC.

1. No HACS, abra **Repositórios personalizados**.
2. Adicione `https://github.com/eduardobittencourt/tuya-camera-ha` como **Integração**.
3. Escolha a release estável `0.3.1`; não é preciso habilitar versões beta.
4. Baixe a integração e reinicie o HA.
5. Vá a **Configurações → Dispositivos e serviços → Adicionar integração** e
   procure **Tuya Camera Bridge**.
6. Escolha Tuya Smart ou Smart Life e informe a conta, a senha e o código de
   país usados no aplicativo. Para o Brasil, use `55`.
7. Abra a câmera e ative o som no player.

Uma release em rascunho não pode ser baixada publicamente. A primeira instalação
precisa dos binários publicados no GitHub; uma branch de desenvolvimento pode
referenciar arquivos ainda não publicados. O repositório é adicionado manualmente
ao HACS e ainda não está no catálogo padrão.

## Câmera testada

A **Positivo Casa Inteligente Smart Câmera Wi-Fi com Bateria (11188736)**,
com firmware **1.1.48**, foi testada pelo Tuya Smart no HA OS 2026.9.4.
Vídeo HEVC/1080p, som PCM, capturas de imagem, recuperação do bridge e reprodução
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
