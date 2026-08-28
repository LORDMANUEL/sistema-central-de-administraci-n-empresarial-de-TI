package spool

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"time"
)

type Kind string

const (
	KindTelemetry     Kind = "telemetry"
	KindCommandResult Kind = "command-result"
)

var (
	ErrFull     = errors.New("spool capacity is full")
	ErrConflict = errors.New("spool item ID conflicts with existing payload")
	idPattern   = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`)
)

type Item struct {
	Kind      Kind            `json:"kind"`
	ID        string          `json:"id"`
	Payload   json.RawMessage `json:"payload"`
	CreatedAt time.Time       `json:"created_at"`
}

type Queue struct {
	dir      string
	maxBytes int64
	maxItems int
}

type diskEntry struct {
	Item Item
	path string
	size int64
}

func New(dir string, maxBytes int64, maxItems int) (*Queue, error) {
	if dir == "" || maxBytes <= 0 || maxItems <= 0 {
		return nil, errors.New("invalid spool configuration")
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	return &Queue{dir: dir, maxBytes: maxBytes, maxItems: maxItems}, nil
}

func (q *Queue) Enqueue(item Item) error {
	if item.Kind != KindTelemetry && item.Kind != KindCommandResult {
		return errors.New("invalid spool kind")
	}
	if !idPattern.MatchString(item.ID) {
		return errors.New("invalid spool item ID")
	}
	if len(item.Payload) == 0 || !json.Valid(item.Payload) {
		return errors.New("spool payload must be valid JSON")
	}
	if item.CreatedAt.IsZero() {
		item.CreatedAt = time.Now().UTC()
	} else {
		item.CreatedAt = item.CreatedAt.UTC()
	}
	payload, err := json.Marshal(item)
	if err != nil {
		return err
	}
	path := q.path(item.Kind, item.ID)
	if existing, err := os.ReadFile(path); err == nil {
		if bytes.Equal(existing, payload) {
			return nil
		}
		return ErrConflict
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	entries, total, err := q.entries()
	if err != nil {
		return err
	}
	for len(entries)+1 > q.maxItems || total+int64(len(payload)) > q.maxBytes {
		idx := -1
		for i, entry := range entries {
			if entry.Item.Kind == KindTelemetry {
				idx = i
				break
			}
		}
		if idx < 0 {
			return ErrFull
		}
		if err := os.Remove(entries[idx].path); err != nil {
			return err
		}
		total -= entries[idx].size
		entries = append(entries[:idx], entries[idx+1:]...)
	}
	tmp, err := os.CreateTemp(q.dir, ".spool-*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	ok := false
	defer func() {
		_ = tmp.Close()
		if !ok {
			_ = os.Remove(tmpName)
		}
	}()
	if err := tmp.Chmod(0o600); err != nil {
		return err
	}
	if _, err := tmp.Write(payload); err != nil {
		return err
	}
	if err := tmp.Sync(); err != nil {
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmpName, path); err != nil {
		return err
	}
	ok = true
	return nil
}

func (q *Queue) List() ([]Item, error) {
	entries, _, err := q.entries()
	if err != nil {
		return nil, err
	}
	items := make([]Item, 0, len(entries))
	for _, entry := range entries {
		items = append(items, entry.Item)
	}
	return items, nil
}

func (q *Queue) Ack(kind Kind, id string) error {
	err := os.Remove(q.path(kind, id))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}

func (q *Queue) path(kind Kind, id string) string {
	return filepath.Join(q.dir, fmt.Sprintf("%s-%s.json", kind, id))
}

func (q *Queue) entries() ([]diskEntry, int64, error) {
	matches, err := filepath.Glob(filepath.Join(q.dir, "*.json"))
	if err != nil {
		return nil, 0, err
	}
	entries := make([]diskEntry, 0, len(matches))
	var total int64
	for _, path := range matches {
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, 0, err
		}
		var item Item
		if err := json.Unmarshal(raw, &item); err != nil {
			return nil, 0, fmt.Errorf("corrupt spool item %s: %w", path, err)
		}
		info, err := os.Stat(path)
		if err != nil {
			return nil, 0, err
		}
		entries = append(entries, diskEntry{Item: item, path: path, size: info.Size()})
		total += info.Size()
	}
	sort.Slice(entries, func(i, j int) bool {
		if entries[i].Item.CreatedAt.Equal(entries[j].Item.CreatedAt) {
			return entries[i].path < entries[j].path
		}
		return entries[i].Item.CreatedAt.Before(entries[j].Item.CreatedAt)
	})
	return entries, total, nil
}
