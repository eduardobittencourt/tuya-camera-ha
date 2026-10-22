package tuya

type MQTConfig struct {
	Msid     string `json:"msid"`
	Password string `json:"password"`
}

type Domain struct {
	AispeechHttpsUrl    string `json:"aispeechHttpsUrl"`
	AispeechQuicUrl     string `json:"aispeechQuicUrl"`
	DeviceHttpUrl       string `json:"deviceHttpUrl"`
	DeviceHttpsPskUrl   string `json:"deviceHttpsPskUrl"`
	DeviceHttpsUrl      string `json:"deviceHttpsUrl"`
	DeviceMediaMqttUrl  string `json:"deviceMediaMqttUrl"`
	DeviceMediaMqttsUrl string `json:"deviceMediaMqttsUrl"`
	DeviceMqttsPskUrl   string `json:"deviceMqttsPskUrl"`
	DeviceMqttsUrl      string `json:"deviceMqttsUrl"`
	GwApiUrl            string `json:"gwApiUrl"`
	GwMqttUrl           string `json:"gwMqttUrl"`
	HttpPort            int    `json:"httpPort"`
	HttpsPort           int    `json:"httpsPort"`
	HttpsPskPort        int    `json:"httpsPskPort"`
	MobileApiUrl        string `json:"mobileApiUrl"`
	MobileMediaMqttUrl  string `json:"mobileMediaMqttUrl"`
	MobileMqttUrl       string `json:"mobileMqttUrl"`
	MobileMqttsUrl      string `json:"mobileMqttsUrl"`
	MobileQuicUrl       string `json:"mobileQuicUrl"`
	MqttPort            int    `json:"mqttPort"`
	MqttQuicUrl         string `json:"mqttQuicUrl"`
	MqttsPort           int    `json:"mqttsPort"`
	MqttsPskPort        int    `json:"mqttsPskPort"`
	RegionCode          string `json:"regionCode"`
}

type Device struct {
	Category            string `json:"category"`
	DeviceId            string `json:"deviceId"`
	DeviceName          string `json:"deviceName"`
	P2pType             int    `json:"p2pType"`
	ProductId           string `json:"productId"`
	SupportCloudStorage bool   `json:"supportCloudStorage"`
	Uuid                string `json:"uuid"`
}

type WebRTCConfigResponse struct {
	Result  WebRTCConfig `json:"result"`
	Success bool         `json:"success"`
	Msg     string       `json:"errorMsg,omitempty"`
}

type WebRTCConfig struct {
	AudioAttributes     AudioAttributes `json:"audioAttributes"`
	Auth                string          `json:"auth"`
	GatewayId           string          `json:"gatewayId"`
	Id                  string          `json:"id"`
	LocalKey            string          `json:"localKey"`
	MotoId              string          `json:"motoId"`
	NodeId              string          `json:"nodeId"`
	P2PConfig           P2PConfig       `json:"p2pConfig"`
	ProtocolVersion     string          `json:"protocolVersion"`
	Skill               string          `json:"skill"`
	Sub                 bool            `json:"sub"`
	SupportWebrtcRecord bool            `json:"supportWebrtcRecord"`
	SupportsPtz         bool            `json:"supportsPtz"`
	SupportsWebrtc      bool            `json:"supportsWebrtc"`
	VedioClarity        int             `json:"vedioClarity"`
	VedioClaritys       []int           `json:"vedioClaritys"`
	VideoClarity        int             `json:"videoClarity"`
}

type AudioSkill struct {
	Channels   int `json:"channels"`
	DataBit    int `json:"dataBit"`
	CodecType  int `json:"codecType"`
	SampleRate int `json:"sampleRate"`
}

type VideoSkill struct {
	StreamType int    `json:"streamType"` // 2 = main stream (hd), 4 = sub stream (sd)
	ProfileId  string `json:"profileId,omitempty"`
	CodecType  int    `json:"codecType"` // 2 = H264, 4 = H265
	Width      int    `json:"width"`
	Height     int    `json:"height"`
	SampleRate int    `json:"sampleRate"`
}

type Skill struct {
	WebRTC int          `json:"webrtc"`
	Audios []AudioSkill `json:"audios"`
	Videos []VideoSkill `json:"videos"`
}

type AudioAttributes struct {
	CallMode           []int `json:"callMode"`
	HardwareCapability []int `json:"hardwareCapability"`
}

type P2PConfig struct {
	Auth   string      `json:"auth"`
	Ices   []ICEServer `json:"ices"`
	MotoId string      `json:"motoId"`
}

type ICEServer struct {
	Urls       string `json:"urls"`
	Credential string `json:"credential,omitempty"`
	Username   string `json:"username,omitempty"`
	Ttl        int    `json:"ttl,omitempty"`
}

type DataChannelMessage struct {
	Type string `json:"type"`
	Msg  string `json:"msg"`
}

type RecvMessage struct {
	Video struct {
		SSRC uint32 `json:"ssrc"`
	} `json:"video"`
	Audio struct {
		SSRC uint32 `json:"ssrc"`
	} `json:"audio"`
}
