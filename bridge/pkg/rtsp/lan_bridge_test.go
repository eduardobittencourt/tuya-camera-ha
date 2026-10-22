package rtsp

import (
	"github.com/eduardobittencourt/tuya-camera-ha/bridge/internal/registry"
	"strings"
	"testing"
)

func TestLocalSDPDoesNotUseCloudHEVCProfile(t *testing.T) {
	server := NewRTSPServer(0, nil)
	camera := &registry.CameraInfo{Local: &registry.LocalMedia{}, Skill: `{"videos":[{"streamType":2,"codecType":4}],"audios":[{"codecType":105}]}`}
	sdp := server.generateSDP(camera, "rtsp://127.0.0.1/camera")
	if !strings.Contains(sdp, "H264/90000") || !strings.Contains(sdp, "L16/8000/1") || strings.Contains(sdp, "H265") || strings.Contains(sdp, "backchannel") {
		t.Fatal("LAN SDP leaked incompatible cloud profile")
	}
}
func TestFragmentMarkersDoNotFinishEachPiece(t *testing.T) {
	for _, v := range []struct {
		p   []byte
		end bool
	}{{[]byte{0x7c, 0x85}, false}, {[]byte{0x7c, 0x05}, false}, {[]byte{0x7c, 0x45}, true}, {[]byte{0x67, 0}, false}, {[]byte{0x65, 0}, true}, {nil, false}} {
		if h264End(v.p) != v.end {
			t.Fatal("incorrect access-unit boundary")
		}
	}
}
