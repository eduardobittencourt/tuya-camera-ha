package lan

import (
	"strings"
	"testing"
)

func TestReportsFilterUnknownAndOpaqueDPs(t *testing.T) {
	c := NewClient("synthetic", "test-lan-key1234", "test", "user", "192.168.0.81", nil, nil)
	c.DPIDs = []int{108, 145}
	c.report(map[string]any{"108": "0", "145": true, "999": "opaque alarm", "111": map[string]any{"private": "discard"}})
	report := c.ReceiveDPS()
	if len(report) != 2 || report["108"] != "0" || report["145"] != true {
		t.Fatal("wrong filtered report")
	}
	c.report(map[string]any{"108": strings.Repeat("x", 257)})
	if c.DPS()["108"] != "0" {
		t.Fatal("oversized opaque value retained")
	}
	snapshot := c.DPS()
	snapshot["108"] = "changed"
	if c.DPS()["108"] != "0" {
		t.Fatal("snapshot aliases state")
	}
	if c.SetDP("999", true) == nil {
		t.Fatal("unknown DP command accepted")
	}
}
func TestNative33ControlHasVersionPrefix(t *testing.T) {
	raw, err := pack33([]byte("test-lan-key1234"), 1, 7, []byte(`{"dps":{"108":"0"}}`))
	if err != nil || string(raw[16:19]) != "3.3" {
		t.Fatal("CONTROL must include clear version prefix")
	}
}

func TestNestedPushAndOpaqueValues(t *testing.T) {
	got := decodeDPS([]byte(`{"protocol":4,"data":{"dps":{"108":"0","145":10}}}`))
	if got["108"] != "0" || got["145"] != float64(10) {
		t.Fatal("nested DP report lost")
	}
}
