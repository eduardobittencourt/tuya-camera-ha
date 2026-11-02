<p align="center">
  <img src="../../custom_components/tuya_camera/brand/icon.png" alt="Ícone Tuya Camera" width="128">
</p>

<h1 align="center">Tuya Camera para Home Assistant</h1>

Conecte câmeras compatíveis do Tuya Smart e Smart Life pelo Home Assistant.

[English](../../README.md) · [Documentação](../README.md) · [Histórico](../../CHANGELOG.md)

## Recursos

- Câmeras nativas, vídeo ao vivo com áudio e capturas JPEG novas.
- Reprodução por HLS e WebRTC pelos componentes do Home Assistant.
- Login, descoberta de câmeras, reconfiguração e renovação da autenticação.
- Vídeo H.264 sem reconversão e H.265 convertido para H.264.
- [Controles e telemetria LAN](entities.md) conforme o modelo.

Os protocolos executam em Python dentro da integração, usando o FFmpeg do HA.
A configuração é pela interface, sem add-on separado, ONVIF ou IDs manuais.

## Requisitos

Home Assistant **2026.9 ou mais recente em Linux**, câmera compatível vinculada
ao Tuya Smart ou Smart Life, internet para autenticação e sinalização e FFmpeg
com suporte H.264/AAC. HA OS e Container já incluem FFmpeg.

## Instalação

Disponível no **catálogo padrão do HACS**.

[![Abrir no HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=tuya-camera-ha&category=integration)

1. No **HACS**, procure **Tuya Camera** e baixe a versão estável mais recente.
2. Reinicie o HA.
3. Abra **Configurações → Dispositivos e serviços → Adicionar integração → Tuya Camera**.

Consulte [instalação](installation.md) para o procedimento manual e
[migração](migrations.md) para atualizar o antigo **Tuya Camera Bridge**.

## Configuração

Escolha Tuya Smart ou Smart Life e informe a conta, senha e código de país usados
no aplicativo (`55` para o Brasil). Abra uma câmera e ative o som no player.
Use **Reconfigurar** para atualizar a lista de câmeras ou entrar novamente.

## Compatibilidade e limitações

A **Positivo Casa Inteligente Smart Câmera Wi-Fi com Bateria (11188736)** foi
testada. Consulte [compatibilidade](compatibility.md) para firmware e resultados.
Descoberta não comprova reprodução de vídeo.

- APIs privadas da Tuya podem mudar; modelo, firmware e aplicativo afetam o suporte.
- Autenticação e sinalização exigem internet. A mídia pode ser direta ou por TURN;
  funcionamento totalmente offline não foi estabelecido.
- PTZ, áudio bidirecional, MFA e captcha interativos não são suportados.
- Câmeras a bateria podem depender de despertar pela nuvem. Autonomia e ciclos
  longos de repouso não foram medidos; a primeira captura pode exceder o tempo do HA.
- A conversão H.265 usa software e pode pesar em hosts pequenos.

## Suporte e segurança

Consulte [resolução de problemas](troubleshooting.md) e [suporte](../../SUPPORT.md).
Não publique credenciais, sessões, IDs, capturas brutas, imagens privadas ou backups.
A senha não é salva; sessões ficam no armazenamento privado do HA. Proteja a
configuração e os backups. Relate vulnerabilidades em particular: [SECURITY.md](../../SECURITY.md).

## Contribuição

Relatos de compatibilidade, correções de documentação e código são bem-vindos.
Veja [CONTRIBUTING.md](../../CONTRIBUTING.md), [desenvolvimento](../development/testing.md)
e [Código de Conduta](../../CODE_OF_CONDUCT.md).

## Licença e atribuição

Código original sob [MIT](../../LICENSE), com avisos de terceiros em [NOTICE](../../NOTICE).
Nomes e imagens pertencem aos respectivos titulares; veja a
[origem das imagens](../../custom_components/tuya_camera/BRAND_ASSETS.md).
Projeto independente, sem vínculo ou endosso da Tuya ou do Home Assistant.
