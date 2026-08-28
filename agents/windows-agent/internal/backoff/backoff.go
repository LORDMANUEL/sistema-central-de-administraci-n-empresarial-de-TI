package backoff

import (
	"math/rand/v2"
	"time"
)

type Backoff struct {
	base    time.Duration
	max     time.Duration
	random  func() float64
	attempt uint
}

func New(base, max time.Duration, random func() float64) *Backoff {
	if base <= 0 {
		base = time.Second
	}
	if max < base {
		max = base
	}
	if random == nil {
		random = rand.Float64
	}
	return &Backoff{base: base, max: max, random: random}
}

func (b *Backoff) Next() time.Duration {
	value := b.base
	for i := uint(0); i < b.attempt && value < b.max; i++ {
		if value > b.max/2 {
			value = b.max
			break
		}
		value *= 2
	}
	if value > b.max {
		value = b.max
	}
	r := b.random()
	if r < 0 {
		r = 0
	}
	if r > 1 {
		r = 1
	}
	jittered := time.Duration(float64(value) * (0.5 + r))
	if jittered > b.max {
		jittered = b.max
	}
	b.attempt++
	return jittered
}

func (b *Backoff) Reset() { b.attempt = 0 }
