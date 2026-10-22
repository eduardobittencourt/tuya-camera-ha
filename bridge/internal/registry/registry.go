// Package registry holds the managed account's camera routing in memory only.
package registry

type UserSession struct{ UserKey string }
type LocalMedia struct {
	DPIDs    []int  `json:"dp_ids"`
	Key      string `json:"local_key"`
	Password string `json:"media_password"`
	Host     string `json:"host"`
	MAC      string `json:"mac"`
}
type CameraInfo struct {
	Local      *LocalMedia
	UID        string
	UserKey    string
	DeviceID   string
	DeviceName string
	Category   string
	RTSPPath   string
	ProductID  string
	UUID       string
	Skill      string
}
type Registry struct{ cameras []CameraInfo }

func NewRegistry(cameras []CameraInfo) *Registry {
	return &Registry{cameras: append([]CameraInfo(nil), cameras...)}
}
func (r *Registry) GetAllCameras() ([]CameraInfo, error) {
	return append([]CameraInfo(nil), r.cameras...), nil
}
func (r *Registry) ListUsers() ([]UserSession, error) {
	return []UserSession{{UserKey: "account"}}, nil
}
