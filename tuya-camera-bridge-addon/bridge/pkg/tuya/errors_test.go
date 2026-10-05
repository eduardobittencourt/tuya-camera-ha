package tuya

import (
	"fmt"
	"testing"
)

func TestAuthenticationErrorsAreRecognizedThroughWrapping(t *testing.T) {
	err := fmt.Errorf("startup: %w", &APIError{Code: "USER_SESSION_LOST", Message: "session lost"})
	if !IsAuthenticationError(err) {
		t.Fatal("expired session was not recognized")
	}
	if IsAuthenticationError(&APIError{Code: "PERMISSION_DENIED", Message: "camera not shared"}) {
		t.Fatal("permission error triggered reauthentication")
	}
	if IsAuthenticationError(fmt.Errorf("network timeout")) {
		t.Fatal("transport error triggered reauthentication")
	}
}
