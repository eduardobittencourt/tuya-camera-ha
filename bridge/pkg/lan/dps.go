package lan

import (
	"encoding/json"
	"errors"
	"strconv"
	"time"
)

func scalar(v any) bool {
	switch x := v.(type) {
	case bool, float64:
		return true
	case string:
		return len(x) <= 256
	}
	return false
}
func (c *Client) allowed(id string) bool {
	for _, index := range c.DPIDs {
		if strconv.Itoa(index) == id {
			return true
		}
	}
	return false
}
func (c *Client) report(values map[string]any) {
	safe := map[string]any{}
	c.dpMu.Lock()
	for id, v := range values {
		if c.allowed(id) && scalar(v) {
			c.dpValues[id] = v
			safe[id] = v
		}
	}
	c.dpMu.Unlock()
	if len(safe) > 0 {
		select {
		case c.reports <- safe:
		default:
		}
	}
}
func (c *Client) DPS() map[string]any {
	c.dpMu.Lock()
	defer c.dpMu.Unlock()
	result := map[string]any{}
	for k, v := range c.dpValues {
		result[k] = v
	}
	return result
}
func (c *Client) ReceiveDPS() map[string]any {
	timer := time.NewTimer(100 * time.Millisecond)
	defer timer.Stop()
	select {
	case report := <-c.reports:
		return report
	case <-timer.C:
		return nil
	}
}
func (c *Client) SetDP(id string, value any) error {
	if !c.allowed(id) || !scalar(value) {
		return errors.New("invalid DP command")
	}
	body, _ := json.Marshal(map[string]any{"devId": c.DeviceID, "dps": map[string]any{id: value}, "t": strconv.FormatInt(time.Now().Unix(), 10), "uid": c.UID})
draining:
	for {
		select {
		case <-c.reports:
		default:
			break draining
		}
	}
	return c.session.Send(7, nil, body)
}

func decodeDPS(body []byte) map[string]any {
	var report struct {
		DPS  map[string]any `json:"dps"`
		Data struct {
			DPS map[string]any `json:"dps"`
		} `json:"data"`
	}
	if json.Unmarshal(body, &report) != nil {
		return nil
	}
	if len(report.DPS) > 0 {
		return report.DPS
	}
	return report.Data.DPS
}
