package tuya

import (
	"bytes"
	"compress/gzip"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/md5"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
)

type MobileSDKClient struct {
	SigningKey        string
	SID               string
	AppKey            string
	DeviceID          string // phone device ID
	ChKey             string
	TTID              string
	BaseURL           string
	AppVersion        string
	SDKVersion        string
	DeviceCoreVersion string
	Channel           string
	OSSystem          string
	Platform          string
	AppRNVersion      string
	ET                string
	Ecode             string
	PartnerIdentity   string
	UID               string
	PackageName       string
	Timezone          string
}

var signKeyWhitelist = []string{
	"a", "v", "lat", "lon", "lang", "deviceId", "appVersion", "ttid",
	"isH5", "h5Token", "os", "clientId", "postData", "time", "requestId",
	"et", "n4h5", "sid", "chKey", "sp",
}

// DefaultAPIHost is the Central Europe data center, used when the integration
// did not report a host (config files written before data-center routing).
const DefaultAPIHost = "a1.tuyaeu.com"

// NormalizeAPIHost reduces a configured value to a bare API host, accepting
// both "a1.tuyaus.com" and "https://a1.tuyaus.com/api.json".
func NormalizeAPIHost(host string) string {
	h := strings.TrimSpace(host)
	h = strings.TrimPrefix(h, "https://")
	h = strings.TrimPrefix(h, "http://")
	if i := strings.Index(h, "/"); i >= 0 {
		h = h[:i]
	}
	if h == "" {
		return DefaultAPIHost
	}
	return h
}

// APIBaseURL builds the mobile SDK endpoint for a Tuya API host. A Tuya session
// is only valid in the data center that issued it, so the bridge must talk to
// the same host the integration logged in against (issues #44, #58).
func APIBaseURL(host string) string {
	return fmt.Sprintf("https://%s/api.json", NormalizeAPIHost(host))
}

func NewMobileSDKClient(signingKey, sid, appKey, deviceID, chKey string) *MobileSDKClient {
	return &MobileSDKClient{
		SigningKey:        signingKey,
		SID:               sid,
		AppKey:            appKey,
		DeviceID:          deviceID,
		ChKey:             chKey,
		TTID:              fmt.Sprintf("sdk_international@%s", appKey),
		BaseURL:           APIBaseURL(""),
		AppVersion:        "1.8.0",
		SDKVersion:        "6.7.0",
		DeviceCoreVersion: "6.7.0",
		Channel:           "oem",
		OSSystem:          "14",
		Platform:          "tuya_bridge",
		AppRNVersion:      "5.92",
		ET:                "0.0.1",
		Timezone:          "UTC",
	}
}

// AppProfile carries the versioned public identity of the selected Tuya app.
type AppProfile struct {
	AppVersion        string
	SDKVersion        string
	DeviceCoreVersion string
	TTID              string
	Channel           string
	OSSystem          string
	Platform          string
	AppRNVersion      string
	ET                string
}

// ApplyAppProfile replaces defaults only when the integration supplied a value.
func (c *MobileSDKClient) ApplyAppProfile(profile AppProfile) {
	if profile.AppVersion != "" {
		c.AppVersion = profile.AppVersion
	}
	if profile.SDKVersion != "" {
		c.SDKVersion = profile.SDKVersion
	}
	if profile.DeviceCoreVersion != "" {
		c.DeviceCoreVersion = profile.DeviceCoreVersion
	}
	if profile.TTID != "" {
		c.TTID = profile.TTID
	}
	if profile.Channel != "" {
		c.Channel = profile.Channel
	}
	if profile.OSSystem != "" {
		c.OSSystem = profile.OSSystem
	}
	if profile.Platform != "" {
		c.Platform = profile.Platform
	}
	if profile.AppRNVersion != "" {
		c.AppRNVersion = profile.AppRNVersion
	}
	if profile.ET != "" {
		c.ET = profile.ET
	}
}

func swapSignString(s string) string {
	if len(s) != 32 {
		return s
	}
	return s[8:16] + s[0:8] + s[24:32] + s[16:24]
}

func (c *MobileSDKClient) sign(params map[string]string) string {
	whiteset := make(map[string]bool)
	for _, k := range signKeyWhitelist {
		whiteset[k] = true
	}

	filtered := make(map[string]string)
	for k, v := range params {
		if whiteset[k] && v != "" {
			filtered[k] = v
		}
	}

	if pd, ok := filtered["postData"]; ok && pd != "" {
		h := md5.Sum([]byte(pd))
		filtered["postData"] = swapSignString(hex.EncodeToString(h[:]))
	}

	keys := make([]string, 0, len(filtered))
	for k := range filtered {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	parts := make([]string, len(keys))
	for i, k := range keys {
		parts[i] = k + "=" + filtered[k]
	}
	signStr := strings.Join(parts, "||")

	key := []byte(c.SigningKey)
	if c.ET == "3" {
		digest := sha256.Sum256(key)
		key = digest[:]
	}
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte(signStr))
	return hex.EncodeToString(mac.Sum(nil))
}

func (c *MobileSDKClient) payloadKey(requestID string) []byte {
	material := c.SigningKey
	if c.Ecode != "" {
		material += "_" + c.Ecode
	}
	mac := hmac.New(sha256.New, []byte(requestID))
	mac.Write([]byte(material))
	digest := hex.EncodeToString(mac.Sum(nil))
	return []byte(digest[:16])
}

func encryptMobilePayload(key []byte, value interface{}) (string, error) {
	plain, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}
	sealed := gcm.Seal(nil, nonce, plain, nil)
	return base64.StdEncoding.EncodeToString(append(nonce, sealed...)), nil
}

func decryptMobilePayload(key []byte, value string) (json.RawMessage, error) {
	raw, err := base64.StdEncoding.DecodeString(value)
	if err != nil {
		return nil, fmt.Errorf("decode encrypted response: %w", err)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	if len(raw) < gcm.NonceSize() {
		return nil, fmt.Errorf("encrypted response is shorter than the nonce")
	}
	plain, err := gcm.Open(nil, raw[:gcm.NonceSize()], raw[gcm.NonceSize():], nil)
	if err != nil {
		return nil, fmt.Errorf("decrypt response: %w", err)
	}
	reader, err := gzip.NewReader(bytes.NewReader(plain))
	if err == nil {
		decompressed, readErr := io.ReadAll(reader)
		closeErr := reader.Close()
		if readErr != nil {
			return nil, fmt.Errorf("decompress response: %w", readErr)
		}
		if closeErr != nil {
			return nil, fmt.Errorf("close gzip response: %w", closeErr)
		}
		plain = decompressed
	}
	if !json.Valid(plain) {
		return nil, fmt.Errorf("decrypted response is not valid JSON")
	}
	return json.RawMessage(plain), nil
}

func (c *MobileSDKClient) buildParams(action, version string, postData interface{}) (map[string]string, []byte, error) {
	requestID := uuid.New().String()
	params := map[string]string{
		"a":                 action,
		"v":                 version,
		"time":              fmt.Sprintf("%d", time.Now().Unix()),
		"appVersion":        c.AppVersion,
		"appRnVersion":      c.AppRNVersion,
		"channel":           c.Channel,
		"chKey":             c.ChKey,
		"clientId":          c.AppKey,
		"cp":                "gzip",
		"deviceCoreVersion": c.DeviceCoreVersion,
		"deviceId":          c.DeviceID,
		"et":                c.ET,
		"nd":                "1",
		"lang":              "en",
		"os":                "Android",
		"osSystem":          c.OSSystem,
		"platform":          c.Platform,
		"requestId":         requestID,
		"sdkVersion":        c.SDKVersion,
		"sid":               c.SID,
		"timeZoneId":        c.Timezone,
		"ttid":              c.TTID,
	}

	var key []byte
	if c.ET == "3" {
		key = c.payloadKey(requestID)
		if postData == nil {
			postData = map[string]interface{}{}
		}
		encrypted, err := encryptMobilePayload(key, postData)
		if err != nil {
			return nil, nil, fmt.Errorf("encrypt request: %w", err)
		}
		params["postData"] = encrypted
	} else if postData != nil {
		var pdStr string
		switch v := postData.(type) {
		case string:
			pdStr = v
		default:
			b, _ := json.Marshal(v)
			pdStr = string(b)
		}
		params["postData"] = pdStr
	}

	params["sign"] = c.sign(params)
	return params, key, nil
}

func (c *MobileSDKClient) Call(action, version string, postData interface{}) (json.RawMessage, error) {
	params, payloadKey, err := c.buildParams(action, version, postData)
	if err != nil {
		return nil, err
	}

	form := url.Values{}
	for k, v := range params {
		form.Set(k, v)
	}

	req, err := http.NewRequest("POST", c.BaseURL, strings.NewReader(form.Encode()))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("User-Agent", fmt.Sprintf("Thing-UA=APP/Android/%s/SDK/%s", c.AppVersion, c.SDKVersion))

	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	if c.ET == "3" {
		return parseEncryptedAPIResponse(body, payloadKey)
	}
	return parseAPIResponse(body)
}

func parseEncryptedAPIResponse(body, key []byte) (json.RawMessage, error) {
	var envelope struct {
		Result    json.RawMessage `json:"result"`
		ErrorCode string          `json:"errorCode,omitempty"`
		ErrorMsg  string          `json:"errorMsg,omitempty"`
		Code      string          `json:"code,omitempty"`
		Msg       string          `json:"msg,omitempty"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil, fmt.Errorf("JSON decode error: %w", err)
	}
	if len(envelope.Result) == 0 || bytes.Equal(envelope.Result, []byte("null")) {
		code := envelope.ErrorCode
		if code == "" {
			code = envelope.Code
		}
		message := envelope.ErrorMsg
		if message == "" {
			message = envelope.Msg
		}
		if code == "" {
			code = "unknown"
		}
		if message == "" {
			message = "no result"
		}
		return nil, fmt.Errorf("API error: %s (code: %s)", message, code)
	}
	var encrypted string
	if err := json.Unmarshal(envelope.Result, &encrypted); err != nil {
		return nil, fmt.Errorf("encrypted API result is not a string: %w", err)
	}
	decrypted, err := decryptMobilePayload(key, encrypted)
	if err != nil {
		return nil, err
	}
	return unwrapEncryptedResult(decrypted)
}

func unwrapEncryptedResult(raw json.RawMessage) (json.RawMessage, error) {
	var envelope struct {
		Result    json.RawMessage `json:"result"`
		Success   *bool           `json:"success,omitempty"`
		ErrorCode string          `json:"errorCode,omitempty"`
		ErrorMsg  string          `json:"errorMsg,omitempty"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return nil, fmt.Errorf("decrypted JSON decode error: %w", err)
	}
	if envelope.Success != nil && !*envelope.Success {
		code := envelope.ErrorCode
		if code == "" {
			code = "unknown"
		}
		message := envelope.ErrorMsg
		if message == "" {
			message = "no result"
		}
		return nil, fmt.Errorf("API error: %s (code: %s)", message, code)
	}
	if len(envelope.Result) != 0 && !bytes.Equal(envelope.Result, []byte("null")) {
		return envelope.Result, nil
	}
	return raw, nil
}

// parseAPIResponse decodes a Tuya api.json response, surfacing the machine-readable
// errorCode alongside errorMsg so opaque failures (e.g. "No access") can be diagnosed.
func parseAPIResponse(body []byte) (json.RawMessage, error) {
	var result struct {
		Result    json.RawMessage `json:"result"`
		Success   bool            `json:"success"`
		ErrorCode string          `json:"errorCode,omitempty"`
		ErrorMsg  string          `json:"errorMsg,omitempty"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("JSON decode error: %w", err)
	}
	if !result.Success {
		if result.ErrorCode != "" {
			return nil, fmt.Errorf("API error: %s (code: %s)", result.ErrorMsg, result.ErrorCode)
		}
		return nil, fmt.Errorf("API error: %s", result.ErrorMsg)
	}
	return result.Result, nil
}

// P2PPreLink signals the intent to stream from a device before asking for its
// WebRTC config, the way the vendor app does.
//
// The action name and the devId payload come from the app capture recorded in
// WHITEPAPER.md and from examples/tuya_client.py. This used to call
// `thing.m.p2p.main.pre.link.get` with no payload, which the server rejects; the
// failure was logged as non-fatal and ignored. On devices where Tuya wants the
// pre-link before granting the config, the next call comes back
// PERMISSION_DENIED (issue #48).
func (c *MobileSDKClient) P2PPreLink(deviceID string) error {
	_, err := c.Call("smartlife.m.p2p.main.pre.link.get", "1.0", map[string]string{"devId": deviceID})
	return err
}

func (c *MobileSDKClient) RTCSessionInit(deviceID string) error {
	_, err := c.Call("smartlife.m.rtc.session.init", "1.0", map[string]string{"devId": deviceID})
	return err
}

func (c *MobileSDKClient) GetWebRTCConfig(deviceID string) (*WebRTCConfigResponse, error) {
	raw, err := c.Call("smartlife.m.rtc.config.get", "1.0", map[string]string{"devId": deviceID})
	if err != nil {
		return nil, err
	}
	var config WebRTCConfig
	if err := json.Unmarshal(raw, &config); err != nil {
		return nil, err
	}
	return &WebRTCConfigResponse{Result: config, Success: true}, nil
}

func (c *MobileSDKClient) DeriveMQTTConfig(ecode string) *MQTConfig {
	md5SignKey := fmt.Sprintf("%x", md5.Sum([]byte(c.SigningKey)))
	pwFull := fmt.Sprintf("%x", md5.Sum([]byte(md5SignKey+ecode)))
	password := pwFull[8:24]
	md5AppKey := fmt.Sprintf("%x", md5.Sum([]byte(c.AppKey)))
	userTail := fmt.Sprintf("%x", md5.Sum([]byte(md5AppKey+ecode)))
	msid := userTail[len(userTail)-16:]
	return &MQTConfig{Msid: msid, Password: password}
}

func (c *MobileSDKClient) DeriveMQTTUsername(sid, ecode, partnerIdentity string) string {
	md5AppKey := fmt.Sprintf("%x", md5.Sum([]byte(c.AppKey)))
	userTail := fmt.Sprintf("%x", md5.Sum([]byte(md5AppKey+ecode)))
	return fmt.Sprintf("%s_v1_%s_%s_mb_%s%s",
		partnerIdentity, c.AppKey, c.ChKey, sid, userTail[len(userTail)-16:])
}

func (c *MobileSDKClient) DeriveMQTTClientID(uid string) string {
	uidHash := fmt.Sprintf("%x", md5.Sum([]byte(uid+"sdkfasodifca")))
	pkg := c.PackageName
	if pkg == "" {
		pkg = "tuya_bridge"
	}
	return fmt.Sprintf("%s_mb_%s_%s_DEFAULT", pkg, c.DeviceID, uidHash)
}

func (c *MobileSDKClient) GetUserInfo() (*UserInfoResult, error) {
	raw, err := c.Call("smartlife.m.user.info.get", "1.0", nil)
	if err != nil {
		return nil, err
	}
	var info UserInfoResult
	if err := json.Unmarshal(raw, &info); err != nil {
		return nil, err
	}
	return &info, nil
}

func (c *MobileSDKClient) GetDeviceInfo(deviceID string) (json.RawMessage, error) {
	return c.Call("tuya.m.device.get", "1.0", map[string]string{"devId": deviceID})
}

type UserInfoResult struct {
	ID         string `json:"id"`
	Email      string `json:"email"`
	Nickname   string `json:"nickname"`
	TimezoneId string `json:"timezoneId"`
	Domain     Domain `json:"domain"`
}
