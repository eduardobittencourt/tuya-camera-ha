// (c) go2rtc; adapted to support cancellation without leaking goroutines.
package utils

import (
	"context"
	"sync"
)

type Waiter struct {
	mu    sync.Mutex
	state int
	err   error
	done  chan struct{}
}

func (w *Waiter) channel() <-chan struct{} {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.done == nil {
		w.done = make(chan struct{})
	}
	if w.state == 0 {
		w.state = 1
	}
	return w.done
}

func (w *Waiter) Add(delta int) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.state >= 0 {
		w.state += delta
	}
}

func (w *Waiter) Wait() error { return w.WaitContext(context.Background()) }

func (w *Waiter) WaitContext(ctx context.Context) error {
	select {
	case <-w.channel():
		w.mu.Lock()
		defer w.mu.Unlock()
		return w.err
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (w *Waiter) Done(err error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.state < 0 {
		return
	}
	if w.done == nil {
		w.done = make(chan struct{})
	}
	if w.state > 0 {
		w.state--
	}
	if w.state == 0 {
		w.state = -1
		w.err = err
		close(w.done)
	}
}

func (w *Waiter) WaitChan() <-chan error {
	ch := make(chan error, 1)
	go func() { ch <- w.Wait(); close(ch) }()
	return ch
}
