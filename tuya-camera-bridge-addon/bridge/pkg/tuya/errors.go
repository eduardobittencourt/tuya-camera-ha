package tuya

import (
	"errors"
	"fmt"
	"strings"
)

// APIError retains the machine-readable code without retaining a response body.
type APIError struct{ Code, Message string }

func (e *APIError) Error() string {
	return fmt.Sprintf("Tuya API error: %s (code: %s)", e.Message, e.Code)
}

func IsAuthenticationError(err error) bool {
	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		return false
	}
	switch strings.ToUpper(apiErr.Code) {
	case "USER_SESSION_LOST", "USER_SESSION_INVALID", "USER_SESSION_EXPIRED", "USER_SESSION_NOT_EXIST", "SESSION_INVALID", "SID_INVALID", "USER_LOGIN_TOKEN_EXPIRED":
		return true
	}
	return false
}
