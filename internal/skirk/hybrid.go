package skirk

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"sort"
)

const (
	controlPrefix = "control"
	dataPrefix    = "data"
)

type HybridSendResult struct {
	SessionID      string   `json:"session_id"`
	Chunks         int      `json:"chunks"`
	BytesPlaintext int64    `json:"bytes_plaintext"`
	DriveObjects   []string `json:"drive_objects"`
	ControlRows    []string `json:"control_rows"`
}

type HybridReceiveResult struct {
	SessionID      string   `json:"session_id"`
	Chunks         int      `json:"chunks"`
	BytesPlaintext int64    `json:"bytes_plaintext"`
	DriveObjects   []string `json:"drive_objects"`
	ControlRows    []string `json:"control_rows"`
}

type ControlPayload struct {
	Version     int    `json:"v"`
	Event       string `json:"event"`
	SessionID   string `json:"session_id"`
	ConnID      string `json:"conn_id,omitempty"`
	Direction   string `json:"direction"`
	Sequence    uint64 `json:"sequence"`
	DriveObject string `json:"drive_object,omitempty"`
	Target      string `json:"target,omitempty"`
	Bytes       int    `json:"bytes,omitempty"`
	Final       bool   `json:"final,omitempty"`
	Error       string `json:"error,omitempty"`
}

func HybridSendFile(ctx context.Context, data BlobStore, control BlobStore, inputPath, secret, sessionID string, direction byte, chunkSize int, cleanupExisting bool) (HybridSendResult, error) {
	if chunkSize <= 0 {
		chunkSize = 8192
	}
	sid, err := ParseSessionID(sessionID)
	if err != nil {
		return HybridSendResult{}, err
	}
	key, err := DeriveKey(secret)
	if err != nil {
		return HybridSendResult{}, err
	}
	if cleanupExisting {
		infos, err := control.List(ctx, fileControlPrefix(sid, direction))
		if err != nil {
			return HybridSendResult{}, err
		}
		for _, info := range infos {
			_ = control.Delete(ctx, info.Name)
		}
	}
	input, err := os.Open(inputPath)
	if err != nil {
		return HybridSendResult{}, err
	}
	defer input.Close()

	var result HybridSendResult
	result.SessionID = SessionString(sid)
	buffer := make([]byte, chunkSize)
	for {
		n, readErr := io.ReadFull(input, buffer)
		if readErr == io.ErrUnexpectedEOF || readErr == io.EOF {
			// Send an explicit final chunk, including a zero-byte chunk for empty files.
		} else if readErr != nil {
			return HybridSendResult{}, readErr
		}
		chunk := buffer[:n]
		final := readErr == io.ErrUnexpectedEOF || readErr == io.EOF
		dataName := fileDataName(sid, direction, uint64(result.Chunks))
		sealed, err := Seal(key, sid, direction, uint64(result.Chunks), chunk, final)
		if err != nil {
			return HybridSendResult{}, err
		}
		if err := data.Put(ctx, dataName, sealed); err != nil {
			return HybridSendResult{}, err
		}
		controlName := fileControlName(sid, direction, uint64(result.Chunks))
		payload := ControlPayload{
			Version:     1,
			Event:       "CHUNK_READY",
			SessionID:   SessionString(sid),
			Direction:   directionName(direction),
			Sequence:    uint64(result.Chunks),
			DriveObject: dataName,
			Bytes:       n,
			Final:       final,
		}
		payloadBytes, err := json.Marshal(payload)
		if err != nil {
			return HybridSendResult{}, err
		}
		if err := control.Put(ctx, controlName, payloadBytes); err != nil {
			return HybridSendResult{}, err
		}
		result.DriveObjects = append(result.DriveObjects, dataName)
		result.ControlRows = append(result.ControlRows, controlName)
		result.BytesPlaintext += int64(n)
		result.Chunks++
		if final {
			break
		}
	}
	return result, nil
}

func HybridReceiveFile(ctx context.Context, data BlobStore, control BlobStore, outputPath, secret, sessionID string, direction byte, deleteAfter bool) (HybridReceiveResult, error) {
	sid, err := ParseSessionID(sessionID)
	if err != nil {
		return HybridReceiveResult{}, err
	}
	key, err := DeriveKey(secret)
	if err != nil {
		return HybridReceiveResult{}, err
	}
	infos, err := control.List(ctx, fileControlPrefix(sid, direction))
	if err != nil {
		return HybridReceiveResult{}, err
	}
	sort.Slice(infos, func(i, j int) bool { return infos[i].Name < infos[j].Name })
	if len(infos) == 0 {
		return HybridReceiveResult{}, fmt.Errorf("no control rows for session %s", sessionID)
	}
	output, err := os.Create(outputPath)
	if err != nil {
		return HybridReceiveResult{}, err
	}
	defer output.Close()

	result := HybridReceiveResult{SessionID: SessionString(sid)}
	expected := uint64(0)
	for _, info := range infos {
		raw, err := control.Get(ctx, info.Name)
		if err != nil {
			return HybridReceiveResult{}, err
		}
		var payload ControlPayload
		if err := json.Unmarshal(raw, &payload); err != nil {
			return HybridReceiveResult{}, err
		}
		if payload.Sequence != expected {
			return HybridReceiveResult{}, fmt.Errorf("missing sequence %d; got %d", expected, payload.Sequence)
		}
		sealed, err := data.Get(ctx, payload.DriveObject)
		if err != nil {
			return HybridReceiveResult{}, err
		}
		env, plaintext, err := OpenEnvelope(key, sealed)
		if err != nil {
			return HybridReceiveResult{}, err
		}
		if env.SessionID != sid || env.Direction != direction || env.Sequence != expected {
			return HybridReceiveResult{}, fmt.Errorf("envelope metadata mismatch for %s", payload.DriveObject)
		}
		if _, err := output.Write(plaintext); err != nil {
			return HybridReceiveResult{}, err
		}
		result.DriveObjects = append(result.DriveObjects, payload.DriveObject)
		result.ControlRows = append(result.ControlRows, info.Name)
		result.BytesPlaintext += int64(len(plaintext))
		result.Chunks++
		expected++
		if payload.Final {
			break
		}
	}
	if deleteAfter {
		for _, name := range result.DriveObjects {
			_ = data.Delete(ctx, name)
		}
		for _, name := range result.ControlRows {
			_ = control.Delete(ctx, name)
		}
	}
	return result, nil
}

func fileDataName(sid [16]byte, direction byte, sequence uint64) string {
	return fmt.Sprintf("%s/%s/%s/%016x.skb", dataPrefix, SessionString(sid), directionName(direction), sequence)
}

func fileControlName(sid [16]byte, direction byte, sequence uint64) string {
	return fmt.Sprintf("%s/%s/%s/%016x", controlPrefix, SessionString(sid), directionName(direction), sequence)
}

func fileControlPrefix(sid [16]byte, direction byte) string {
	return fmt.Sprintf("%s/%s/%s/", controlPrefix, SessionString(sid), directionName(direction))
}

func directionName(direction byte) string {
	if direction == DirectionDown {
		return "down"
	}
	return "up"
}
