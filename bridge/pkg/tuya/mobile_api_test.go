package tuya

import (
	"crypto/hmac"
	"crypto/md5"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"sort"
	"strings"
	"testing"
)

func TestApplyAppProfile(t *testing.T) {
	client := NewMobileSDKClient("signing", "sid", "app", "device", "channel")
	client.ApplyAppProfile(AppProfile{
		AppVersion:        "7.8.6",
		SDKVersion:        "5.24.0",
		DeviceCoreVersion: "5.17.0",
		TTID:              "international",
		Channel:           "sdk",
		OSSystem:          "15",
		Platform:          "y",
		AppRNVersion:      "5.84",
		ET:                "3",
	})

	params, _, err := client.buildParams("test.action", "1.0", nil)
	if err != nil {
		t.Fatalf("buildParams: %v", err)
	}
	if params["appVersion"] != "7.8.6" || params["sdkVersion"] != "5.24.0" {
		t.Fatalf("app profile was not applied: %#v", params)
	}
	if params["deviceCoreVersion"] != "5.17.0" || params["ttid"] != "international" {
		t.Fatalf("SDK profile was not applied: %#v", params)
	}
	if params["channel"] != "sdk" || params["platform"] != "y" || params["et"] != "3" {
		t.Fatalf("request metadata was not applied: %#v", params)
	}
}

func TestParseAPIResponseSurfacesErrorCode(t *testing.T) {
	body := []byte(`{"success":false,"errorMsg":"No access","errorCode":"NO_AUTH"}`)
	_, err := parseAPIResponse(body)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "No access") {
		t.Errorf("error should contain errorMsg: %v", err)
	}
	if !strings.Contains(err.Error(), "NO_AUTH") {
		t.Errorf("error should surface errorCode: %v", err)
	}
}

func TestParseAPIResponseWithoutErrorCode(t *testing.T) {
	body := []byte(`{"success":false,"errorMsg":"No access"}`)
	_, err := parseAPIResponse(body)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if got := err.Error(); got != "API error: No access" {
		t.Errorf("unexpected error message: %q", got)
	}
}

func TestParseAPIResponseSuccess(t *testing.T) {
	body := []byte(`{"success":true,"result":{"motoId":"abc"}}`)
	raw, err := parseAPIResponse(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(string(raw), "motoId") {
		t.Errorf("result not returned: %s", raw)
	}
}

func TestParseAPIResponseShortInvalidBody(t *testing.T) {
	// Must not panic on bodies shorter than the 200-byte snippet cap.
	_, err := parseAPIResponse([]byte(`not json`))
	if err == nil {
		t.Fatal("expected decode error, got nil")
	}
}

func TestNormalizeAPIHost(t *testing.T) {
	cases := map[string]string{
		"a1.tuyaus.com":                  "a1.tuyaus.com",
		"https://a1.tuyain.com/api.json": "a1.tuyain.com",
		"http://a1.tuyacn.com/":          "a1.tuyacn.com",
		"  a1.tuyaeu.com  ":              "a1.tuyaeu.com",
		"":                               DefaultAPIHost,
		"   ":                            DefaultAPIHost,
	}
	for in, want := range cases {
		if got := NormalizeAPIHost(in); got != want {
			t.Errorf("NormalizeAPIHost(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestAPIBaseURL(t *testing.T) {
	if got := APIBaseURL("a1.tuyaus.com"); got != "https://a1.tuyaus.com/api.json" {
		t.Errorf("APIBaseURL = %q", got)
	}
	// An empty host keeps the pre-routing behaviour: Central Europe.
	if got := APIBaseURL(""); got != "https://a1.tuyaeu.com/api.json" {
		t.Errorf("APIBaseURL(\"\") = %q, want the EU host", got)
	}
	// A value already in URL form must not be doubled up.
	if got := APIBaseURL("https://a1.tuyain.com/api.json"); got != "https://a1.tuyain.com/api.json" {
		t.Errorf("APIBaseURL(url) = %q", got)
	}
}

func TestNewMobileSDKClientDefaultsToEU(t *testing.T) {
	c := NewMobileSDKClient("sk", "sid", "ak", "dev", "ch")
	if c.BaseURL != "https://a1.tuyaeu.com/api.json" {
		t.Errorf("BaseURL = %q, want the EU host by default", c.BaseURL)
	}
	if c.Timezone != "UTC" {
		t.Errorf("Timezone = %q, want UTC by default", c.Timezone)
	}
}

func TestBuildParamsUsesConfiguredTimezone(t *testing.T) {
	c := NewMobileSDKClient("sk", "sid", "ak", "dev", "ch")
	c.Timezone = "America/Sao_Paulo"
	params, _, err := c.buildParams("test.action", "1.0", nil)
	if err != nil {
		t.Fatalf("buildParams: %v", err)
	}
	if got := params["timeZoneId"]; got != "America/Sao_Paulo" {
		t.Errorf("timeZoneId = %q", got)
	}
}

func TestEncryptedMobileCallMatchesPythonClientProtocol(t *testing.T) {
	c := NewMobileSDKClient("global-material", "sid", "app", "device", "channel")
	c.ET = "3"
	c.Ecode = "encryption-code"

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			t.Errorf("ParseForm: %v", err)
		}
		requestID := r.PostForm.Get("requestId")
		key := c.payloadKey(requestID)
		payload, err := decryptMobilePayload(key, r.PostForm.Get("postData"))
		if err != nil {
			t.Errorf("decrypt request: %v", err)
		}
		if string(payload) != `{}` {
			t.Errorf("payload = %s, want {}", payload)
		}

		canonical := make(url.Values)
		for name, values := range r.PostForm {
			if name != "sign" {
				canonical[name] = values
			}
		}
		params := make(map[string]string, len(canonical))
		for name := range canonical {
			params[name] = canonical.Get(name)
		}
		gotSign := r.PostForm.Get("sign")
		digest := sha256.Sum256([]byte(c.SigningKey))
		mac := hmac.New(sha256.New, digest[:])
		mac.Write([]byte(canonicalSignString(params)))
		wantSign := hex.EncodeToString(mac.Sum(nil))
		if gotSign != wantSign {
			t.Errorf("sign = %q, want %q", gotSign, wantSign)
		}

		encrypted, err := encryptMobilePayload(key, map[string]interface{}{
			"success": true,
			"result":  map[string]interface{}{"time": 123},
		})
		if err != nil {
			t.Errorf("encrypt response: %v", err)
		}
		_ = json.NewEncoder(w).Encode(map[string]string{"result": encrypted})
	}))
	defer srv.Close()
	c.BaseURL = srv.URL

	raw, err := c.Call("smartlife.p.time.get", "1.0", nil)
	if err != nil {
		t.Fatalf("Call: %v", err)
	}
	if string(raw) != `{"time":123}` {
		t.Errorf("result = %s", raw)
	}
}

func TestUnwrapEncryptedResultKeepsDirectPayload(t *testing.T) {
	raw, err := unwrapEncryptedResult(json.RawMessage(`{"time":123}`))
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"time":123}` {
		t.Errorf("result = %s", raw)
	}
}

func TestUnwrapEncryptedResultSurfacesInnerError(t *testing.T) {
	_, err := unwrapEncryptedResult(json.RawMessage(
		`{"success":false,"errorCode":"NO_AUTH","errorMsg":"No access"}`,
	))
	if err == nil || !strings.Contains(err.Error(), "NO_AUTH") {
		t.Fatalf("expected inner API error, got %v", err)
	}
}

func canonicalSignString(params map[string]string) string {
	filtered := make(map[string]string)
	for _, key := range signKeyWhitelist {
		if value := params[key]; value != "" {
			filtered[key] = value
		}
	}
	if value := filtered["postData"]; value != "" {
		filtered["postData"] = swapSignString(md5Hex(value))
	}
	keys := make([]string, 0, len(filtered))
	for key := range filtered {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, key+"="+filtered[key])
	}
	return strings.Join(parts, "||")
}

func md5Hex(value string) string {
	digest := md5.Sum([]byte(value))
	return hex.EncodeToString(digest[:])
}

// captureRequest points a client at a test server and returns the form values
// of the single call made against it.
func captureRequest(t *testing.T, call func(c *MobileSDKClient) error) url.Values {
	t.Helper()
	var got url.Values
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			t.Errorf("ParseForm: %v", err)
		}
		got = r.PostForm
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"result":{}}`))
	}))
	defer srv.Close()

	c := NewMobileSDKClient("sk", "sid", "ak", "dev", "ch")
	c.BaseURL = srv.URL
	if err := call(c); err != nil {
		t.Fatalf("call: %v", err)
	}
	return got
}

func TestP2PPreLinkMatchesTheAppCapture(t *testing.T) {
	// Action name and payload come from the app capture in WHITEPAPER.md. The
	// old thing.m.p2p.main.pre.link.get with no devId was rejected, and the
	// server then refused the WebRTC config with PERMISSION_DENIED (issue #48).
	form := captureRequest(t, func(c *MobileSDKClient) error {
		return c.P2PPreLink("bfd705823638458c46rqoi")
	})

	if got := form.Get("a"); got != "smartlife.m.p2p.main.pre.link.get" {
		t.Errorf("action = %q, want smartlife.m.p2p.main.pre.link.get", got)
	}
	if got := form.Get("postData"); got != `{"devId":"bfd705823638458c46rqoi"}` {
		t.Errorf("postData = %q, want the devId payload", got)
	}
	if form.Get("sign") == "" {
		t.Error("request must be signed")
	}
}

func TestWebRTCConfigRequestShape(t *testing.T) {
	form := captureRequest(t, func(c *MobileSDKClient) error {
		_, err := c.GetWebRTCConfig("bfd705823638458c46rqoi")
		return err
	})

	if got := form.Get("a"); got != "smartlife.m.rtc.config.get" {
		t.Errorf("action = %q", got)
	}
	if got := form.Get("postData"); got != `{"devId":"bfd705823638458c46rqoi"}` {
		t.Errorf("postData = %q", got)
	}
}
