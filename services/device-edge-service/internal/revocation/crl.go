package revocation

import (
	"crypto/x509"
	"errors"
	"math/big"
	"sync"
	"time"
)

type Store struct {
	issuer *x509.Certificate
	mu     sync.RWMutex
	serial map[string]struct{}
	next   time.Time
}

func NewStore(issuer *x509.Certificate) *Store {
	return &Store{issuer: issuer, serial: make(map[string]struct{})}
}

func (s *Store) LoadDER(der []byte) error {
	if s == nil || s.issuer == nil {
		return errors.New("revocation issuer is not configured")
	}
	crl, err := x509.ParseRevocationList(der)
	if err != nil {
		return err
	}
	if err := crl.CheckSignatureFrom(s.issuer); err != nil {
		return err
	}
	now := time.Now()
	if !crl.ThisUpdate.IsZero() && now.Before(crl.ThisUpdate.Add(-2*time.Minute)) {
		return errors.New("revocation list is not yet valid")
	}
	if crl.NextUpdate.IsZero() || now.After(crl.NextUpdate) {
		return errors.New("revocation list is expired")
	}
	next := make(map[string]struct{}, len(crl.RevokedCertificateEntries))
	for _, entry := range crl.RevokedCertificateEntries {
		if entry.SerialNumber != nil {
			next[entry.SerialNumber.Text(16)] = struct{}{}
		}
	}
	s.mu.Lock()
	s.serial = next
	s.next = crl.NextUpdate
	s.mu.Unlock()
	return nil
}

func (s *Store) IsRevoked(serial *big.Int) bool {
	if s == nil || serial == nil {
		return false
	}
	s.mu.RLock()
	_, ok := s.serial[serial.Text(16)]
	s.mu.RUnlock()
	return ok
}

func (s *Store) NextUpdate() time.Time {
	if s == nil {
		return time.Time{}
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.next
}

func (s *Store) Valid(now time.Time) bool {
	if s == nil {
		return false
	}
	s.mu.RLock()
	next := s.next
	s.mu.RUnlock()
	return !next.IsZero() && now.Before(next)
}
