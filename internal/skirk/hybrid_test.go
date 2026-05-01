package skirk

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"testing"
)

func TestHybridSendReceiveWithMemoryStores(t *testing.T) {
	ctx := context.Background()
	data := NewMemoryStore()
	control := NewMemoryStore()
	dir := t.TempDir()
	input := filepath.Join(dir, "input.bin")
	output := filepath.Join(dir, "output.bin")
	payload := bytes.Repeat([]byte("skirk"), 2048)
	if err := os.WriteFile(input, payload, 0600); err != nil {
		t.Fatal(err)
	}
	secret, err := RandomSecret()
	if err != nil {
		t.Fatal(err)
	}
	send, err := HybridSendFile(ctx, data, control, input, secret, "", DirectionUp, 4096, false)
	if err != nil {
		t.Fatal(err)
	}
	if send.Chunks != 3 {
		t.Fatalf("expected 3 chunks including final empty chunk, got %d", send.Chunks)
	}
	recv, err := HybridReceiveFile(ctx, data, control, output, secret, send.SessionID, DirectionUp, true)
	if err != nil {
		t.Fatal(err)
	}
	if recv.BytesPlaintext != int64(len(payload)) {
		t.Fatalf("received %d bytes, want %d", recv.BytesPlaintext, len(payload))
	}
	roundtrip, err := os.ReadFile(output)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(roundtrip, payload) {
		t.Fatal("roundtrip payload mismatch")
	}
	infos, err := data.List(ctx, "data/"+send.SessionID)
	if err != nil {
		t.Fatal(err)
	}
	if len(infos) != 0 {
		t.Fatalf("delete-after left %d data objects", len(infos))
	}
}
