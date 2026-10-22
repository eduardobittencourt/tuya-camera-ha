package utils

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

func TestWaiterCancellation(t *testing.T) {
	var waiter Waiter
	ctx, cancel := context.WithTimeout(t.Context(), 10*time.Millisecond)
	defer cancel()
	if err := waiter.WaitContext(ctx); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("got %v", err)
	}
	waiter.Done(nil)
	if err := waiter.Wait(); err != nil {
		t.Fatal(err)
	}
}

func TestWaiterPublishesErrorBeforeWakingReaders(t *testing.T) {
	for range 100 {
		var waiter Waiter
		expected := errors.New("connection failed")
		var group sync.WaitGroup
		for range 10 {
			group.Go(func() {
				if err := waiter.Wait(); !errors.Is(err, expected) {
					t.Errorf("got %v", err)
				}
			})
		}
		waiter.Done(expected)
		group.Wait()
		waiter.Done(nil)
		if err := waiter.Wait(); !errors.Is(err, expected) {
			t.Fatalf("error overwritten: %v", err)
		}
	}
}
