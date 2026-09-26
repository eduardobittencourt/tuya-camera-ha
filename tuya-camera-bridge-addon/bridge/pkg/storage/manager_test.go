package storage

import "testing"

func TestMergeCameraRegistryRemovesStaleDeviceFromPreviousUserKey(t *testing.T) {
	existing := []CameraInfo{
		{UserKey: "old-key", DeviceID: "camera-1", Skill: ""},
		{UserKey: "other-key", DeviceID: "camera-2", Skill: "other"},
	}
	replacement := []CameraInfo{
		{UserKey: "new-key", DeviceID: "camera-1", Skill: "current"},
	}

	got := mergeCameraRegistry(existing, "new-key", replacement)
	if len(got) != 2 {
		t.Fatalf("camera count = %d, want 2", len(got))
	}
	if got[0].DeviceID != "camera-2" || got[1].DeviceID != "camera-1" {
		t.Fatalf("unexpected cameras: %#v", got)
	}
	if got[1].Skill != "current" {
		t.Fatalf("replacement skill = %q, want current", got[1].Skill)
	}
}

func TestMergeCameraRegistryReplacesCurrentUserList(t *testing.T) {
	existing := []CameraInfo{
		{UserKey: "current", DeviceID: "removed"},
		{UserKey: "other", DeviceID: "preserved"},
	}
	replacement := []CameraInfo{
		{UserKey: "current", DeviceID: "added"},
	}

	got := mergeCameraRegistry(existing, "current", replacement)
	if len(got) != 2 || got[0].DeviceID != "preserved" || got[1].DeviceID != "added" {
		t.Fatalf("unexpected cameras: %#v", got)
	}
}
