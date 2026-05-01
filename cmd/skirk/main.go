package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"time"

	"skirk/internal/skirk"
)

func main() {
	if err := run(os.Args); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	if len(args) < 2 {
		usage()
		return nil
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	switch args[1] {
	case "keygen":
		secret, err := skirk.RandomSecret()
		if err != nil {
			return err
		}
		fmt.Println(secret)
		return nil
	case "workspace":
		return workspace(ctx, args[2:])
	case "hybrid-send":
		return hybridSend(ctx, args[2:])
	case "hybrid-recv":
		return hybridRecv(ctx, args[2:])
	case "e2e":
		return e2e(ctx, args[2:])
	case "serve-client":
		return serveClient(ctx, args[2:])
	case "serve-exit":
		return serveExit(ctx, args[2:])
	case "sample-config":
		return sampleConfig(args[2:])
	default:
		usage()
		return fmt.Errorf("unknown command %q", args[1])
	}
}

func usage() {
	fmt.Println(`skirk commands:
  keygen
  sample-config --out skirk.json --spreadsheet-id SHEET_ID --secret SECRET
  workspace create --config skirk.json --title TITLE --sheet skirk
  workspace delete --config skirk.json --spreadsheet-id SHEET_ID
  hybrid-send --config skirk.json --input file.bin [--session SESSION]
  hybrid-recv --config skirk.json --output file.bin --session SESSION [--delete-after]
  e2e --config skirk.json [--bytes 2048] [--delete-after]
  serve-exit --config skirk.json
  serve-client --config skirk.json [--listen 127.0.0.1:18080]`)
}

func load(path string) (*skirk.Config, *skirk.DriveStore, *skirk.SheetsLog, *skirk.Workspace, error) {
	cfg, err := skirk.LoadConfig(path)
	if err != nil {
		return nil, nil, nil, nil, err
	}
	drive, sheets, workspace, err := skirk.StoresFromConfig(context.Background(), cfg)
	return cfg, drive, sheets, workspace, err
}

func workspace(ctx context.Context, args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("workspace needs create or delete")
	}
	fs := flag.NewFlagSet("workspace "+args[0], flag.ExitOnError)
	configPath := fs.String("config", "skirk.json", "config path")
	title := fs.String("title", "skirk-workspace", "spreadsheet title")
	sheet := fs.String("sheet", "skirk", "sheet title")
	spreadsheetID := fs.String("spreadsheet-id", "", "spreadsheet id")
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}
	_, _, _, workspace, err := load(*configPath)
	if err != nil {
		return err
	}
	switch args[0] {
	case "create":
		id, err := workspace.CreateSpreadsheet(ctx, *title, *sheet)
		if err != nil {
			return err
		}
		return printJSON(map[string]string{"spreadsheet_id": id})
	case "delete":
		id := *spreadsheetID
		if id == "" {
			cfg, err := skirk.LoadConfig(*configPath)
			if err != nil {
				return err
			}
			id = cfg.Sheets.SpreadsheetID
		}
		if id == "" {
			return fmt.Errorf("--spreadsheet-id is required when config has none")
		}
		if err := workspace.DeleteSpreadsheet(ctx, id); err != nil {
			return err
		}
		return printJSON(map[string]string{"deleted_spreadsheet_id": id})
	default:
		return fmt.Errorf("unknown workspace command %q", args[0])
	}
}

func hybridSend(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("hybrid-send", flag.ExitOnError)
	configPath := fs.String("config", "skirk.json", "config path")
	input := fs.String("input", "", "input file")
	session := fs.String("session", "", "session id")
	chunkSize := fs.Int("chunk-size", 0, "chunk size")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *input == "" {
		return fmt.Errorf("--input is required")
	}
	cfg, drive, sheets, _, err := load(*configPath)
	if err != nil {
		return err
	}
	if cfg.Sheets.SpreadsheetID == "" {
		return fmt.Errorf("config.sheets.spreadsheet_id is required")
	}
	size := cfg.Tunnel.ChunkSize
	if *chunkSize > 0 {
		size = *chunkSize
	}
	result, err := skirk.HybridSendFile(ctx, drive, sheets, *input, cfg.Secret, firstNonEmpty(*session, cfg.SessionID), skirk.DirectionUp, size, false)
	if err != nil {
		return err
	}
	return printJSON(result)
}

func hybridRecv(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("hybrid-recv", flag.ExitOnError)
	configPath := fs.String("config", "skirk.json", "config path")
	output := fs.String("output", "", "output file")
	session := fs.String("session", "", "session id")
	deleteAfter := fs.Bool("delete-after", false, "delete data/control after receive")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *output == "" || *session == "" {
		return fmt.Errorf("--output and --session are required")
	}
	cfg, drive, sheets, _, err := load(*configPath)
	if err != nil {
		return err
	}
	if cfg.Sheets.SpreadsheetID == "" {
		return fmt.Errorf("config.sheets.spreadsheet_id is required")
	}
	result, err := skirk.HybridReceiveFile(ctx, drive, sheets, *output, cfg.Secret, *session, skirk.DirectionUp, *deleteAfter)
	if err != nil {
		return err
	}
	return printJSON(result)
}

func e2e(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("e2e", flag.ExitOnError)
	configPath := fs.String("config", "skirk.json", "config path")
	byteCount := fs.Int("bytes", 2048, "random payload size")
	deleteAfter := fs.Bool("delete-after", true, "delete data/control after receive")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, drive, sheets, _, err := load(*configPath)
	if err != nil {
		return err
	}
	if cfg.Sheets.SpreadsheetID == "" {
		return fmt.Errorf("config.sheets.spreadsheet_id is required")
	}
	tmpDir, err := os.MkdirTemp("", "skirk-e2e-*")
	if err != nil {
		return err
	}
	defer os.RemoveAll(tmpDir)
	input := filepath.Join(tmpDir, "input.bin")
	output := filepath.Join(tmpDir, "output.bin")
	payload := make([]byte, *byteCount)
	if _, err := rand.Read(payload); err != nil {
		return err
	}
	if err := os.WriteFile(input, payload, 0600); err != nil {
		return err
	}
	start := time.Now()
	send, err := skirk.HybridSendFile(ctx, drive, sheets, input, cfg.Secret, cfg.SessionID, skirk.DirectionUp, cfg.Tunnel.ChunkSize, false)
	if err != nil {
		return err
	}
	recv, err := skirk.HybridReceiveFile(ctx, drive, sheets, output, cfg.Secret, send.SessionID, skirk.DirectionUp, *deleteAfter)
	if err != nil {
		return err
	}
	roundtrip, err := os.ReadFile(output)
	if err != nil {
		return err
	}
	if !bytes.Equal(payload, roundtrip) {
		return fmt.Errorf("payload mismatch")
	}
	return printJSON(map[string]any{
		"result":         "pass",
		"session_id":     send.SessionID,
		"bytes":          len(payload),
		"send_chunks":    send.Chunks,
		"receive_chunks": recv.Chunks,
		"duration_ms":    time.Since(start).Milliseconds(),
		"delete_after":   *deleteAfter,
		"chunk_size":     cfg.Tunnel.ChunkSize,
		"spreadsheet_id": cfg.Sheets.SpreadsheetID,
	})
}

func serveClient(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("serve-client", flag.ExitOnError)
	configPath := fs.String("config", "skirk.json", "config path")
	listen := fs.String("listen", "", "SOCKS5 listen address")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, drive, sheets, _, err := load(*configPath)
	if err != nil {
		return err
	}
	if cfg.Sheets.SpreadsheetID == "" {
		return fmt.Errorf("config.sheets.spreadsheet_id is required")
	}
	tunnel, err := skirk.NewTunnel(drive, sheets, cfg)
	if err != nil {
		return err
	}
	addr := firstNonEmpty(*listen, cfg.Tunnel.Listen)
	log.Printf("skirk client SOCKS5 listening on %s session=%s", addr, skirk.SessionString(tunnel.SessionID))
	return tunnel.ServeClient(ctx, addr)
}

func serveExit(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("serve-exit", flag.ExitOnError)
	configPath := fs.String("config", "skirk.json", "config path")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, drive, sheets, _, err := load(*configPath)
	if err != nil {
		return err
	}
	if cfg.Sheets.SpreadsheetID == "" {
		return fmt.Errorf("config.sheets.spreadsheet_id is required")
	}
	tunnel, err := skirk.NewTunnel(drive, sheets, cfg)
	if err != nil {
		return err
	}
	log.Printf("skirk exit polling session=%s", skirk.SessionString(tunnel.SessionID))
	return tunnel.ServeExit(ctx)
}

func sampleConfig(args []string) error {
	fs := flag.NewFlagSet("sample-config", flag.ExitOnError)
	out := fs.String("out", "skirk.json", "output path")
	spreadsheetID := fs.String("spreadsheet-id", "", "spreadsheet id")
	secret := fs.String("secret", "", "secret from keygen")
	session := fs.String("session", "", "fixed 32-hex session id")
	proxy := fs.String("proxy", "socks5h://127.0.0.1:1080", "upstream restricted-network proxy")
	routeMode := fs.String("route-mode", "real_pinned", "route mode: direct, real_pinned, google_front_pinned")
	googleIP := fs.String("google-ip", "216.239.38.120", "Google edge IP for pinned routing")
	if err := fs.Parse(args); err != nil {
		return err
	}
	value := *secret
	if value == "" {
		generated, err := skirk.RandomSecret()
		if err != nil {
			return err
		}
		value = generated
	}
	cfg := skirk.Config{
		Secret:    value,
		SessionID: *session,
		Auth:      skirk.AuthConfig{TokenCommand: "gcloud auth print-access-token"},
		Route:     skirk.RouteConfig{Mode: *routeMode, Proxy: *proxy, GoogleIP: *googleIP, TimeoutSeconds: 240},
		Sheets:    skirk.SheetsConfig{SpreadsheetID: *spreadsheetID, Range: "skirk!A:D"},
		Tunnel:    skirk.TunnelConfig{Listen: "127.0.0.1:18080", ChunkSize: 8192, PollIntervalMS: 1200, CleanupProcessed: true},
	}
	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(*out, data, 0600)
}

func printJSON(value any) error {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(value)
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

var _ = io.Discard
