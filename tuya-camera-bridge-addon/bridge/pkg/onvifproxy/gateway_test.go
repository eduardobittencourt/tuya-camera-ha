package onvifproxy

import (
	"context"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestNewRejectsIncompleteCamera(t *testing.T) {
	_, err := New(Config{Cameras: []Camera{{ID: "id", Name: "Kitchen"}}})
	if err == nil {
		t.Fatal("expected incomplete camera to be rejected")
	}
}

func TestWriteMediaMTXConfig(t *testing.T) {
	dir := t.TempDir()
	gateway, err := New(Config{
		DataDir: dir, SourcePort: 38554, RTSPPort: 48554,
		Cameras: []Camera{{
			ID: "abc", Name: "Câmera Cozinha", SourcePath: "/Câmera_Cozinha", ProxyPath: "tuya_abc",
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	path, err := gateway.writeMediaMTXConfig()
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	text := string(data)
	for _, want := range []string{
		"rtspAddress: :48554", "rtspTransports: [tcp]", "tuya_abc:",
		"rtsp://127.0.0.1:38554/C%C3%A2mera_Cozinha", "libx264", "runOnDemandRestart: true",
	} {
		if !strings.Contains(text, want) {
			t.Errorf("config does not contain %q:\n%s", want, text)
		}
	}
	info, err := os.Stat(filepath.Join(dir, "mediamtx.yml"))
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Errorf("config mode = %o, want 600", info.Mode().Perm())
	}
}

func TestStableUUID(t *testing.T) {
	a := stableUUID("camera-a")
	if a != stableUUID("camera-a") {
		t.Fatal("UUID is not stable")
	}
	if a == stableUUID("camera-b") {
		t.Fatal("different camera IDs produced the same UUID")
	}
	if len(a) != 36 || a[14] != '4' {
		t.Fatalf("invalid UUID shape: %q", a)
	}
}

func TestProbeMatchDeclaresONVIFTypeNamespace(t *testing.T) {
	responder := newDiscoveryResponder(
		"urn:uuid:11111111-2222-4333-8444-555555555555",
		[]string{"onvif://www.onvif.org/Profile/Streaming"},
		8081,
		"",
	)
	response := responder.probeMatch("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "192.0.2.10")
	for _, want := range []string{
		`xmlns:dn="http://www.onvif.org/ver10/network/wsdl"`,
		`<d:Types>dn:NetworkVideoTransmitter tds:Device</d:Types>`,
		`http://192.0.2.10:8081/onvif/device_service`,
		`onvif://www.onvif.org/Profile/Streaming`,
	} {
		if !strings.Contains(response, want) {
			t.Errorf("probe match does not contain %q", want)
		}
	}
}

func TestSnapshotReturnsPersistentCacheWithoutFFmpeg(t *testing.T) {
	dir := t.TempDir()
	cache := filepath.Join(dir, "camera.jpg")
	want := []byte{0xff, 0xd8, 0xff, 0xd9}
	if err := os.WriteFile(cache, want, 0o600); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	backend := &cameraProvider{
		camera: Camera{Name: "Kitchen", ProxyPath: "kitchen"}, ffmpegBin: "/missing/ffmpeg",
		cachePath: cache, ctx: ctx, logger: slog.New(slog.NewTextHandler(os.Stdout, nil)),
	}
	got, err := backend.Snapshot("profile")
	if err != nil {
		t.Fatal(err)
	}
	if string(got.Data) != string(want) || got.ContentType != "image/jpeg" {
		t.Fatalf("snapshot = %#v", got)
	}
}
