package rtsp

import (
	"errors"
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/pkg/lan"
)

// LocalRequest shares the existing signaling socket. It cannot open media or
// invoke a cloud API; the HA consumer must hold its media activity window.
func (s *RTSPServer) LocalRequest(id, operation, index string, ids []int, value any) (any, error) {
	s.mutex.RLock()
	var stream *CameraStream
	for _, candidate := range s.streams {
		if candidate.camera.DeviceID == id {
			stream = candidate
			break
		}
	}
	s.mutex.RUnlock()
	if stream == nil {
		return nil, errors.New("local media inactive")
	}
	stream.mutex.RLock()
	wb := stream.webrtcBridge
	stream.mutex.RUnlock()
	wb.mutex.RLock()
	defer wb.mutex.RUnlock()
	var client *lan.Client = wb.localClient
	if !wb.connected || client == nil {
		return nil, errors.New("local media inactive")
	}
	switch operation {
	case "stats":
		return client.Snapshot(), nil
	case "status":
		return client.DPS(), nil
	case "receive":
		return client.ReceiveDPS(), nil
	case "set":
		return nil, client.SetDP(index, value)
	case "heartbeat":
		return nil, nil
	}
	return nil, errors.New("unsupported local operation")
}
