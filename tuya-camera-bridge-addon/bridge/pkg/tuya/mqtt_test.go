package tuya

import "testing"

func TestMQTTTLSServerNameUsesBrokerHost(t *testing.T) {
	got, err := mqttTLSServerName("ssl://mqtt.example.com:8883")
	if err != nil {
		t.Fatal(err)
	}
	if got != "mqtt.example.com" {
		t.Errorf("server name = %q, want mqtt.example.com", got)
	}
}

func TestMQTTTLSServerNameRejectsMissingHost(t *testing.T) {
	if _, err := mqttTLSServerName("mqtt.example.com:8883"); err == nil {
		t.Fatal("expected a broker URL without a scheme/host to fail")
	}
}
