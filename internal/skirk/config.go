package skirk

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

type Config struct {
	Secret    string       `json:"secret"`
	SessionID string       `json:"session_id,omitempty"`
	Auth      AuthConfig   `json:"auth"`
	Route     RouteConfig  `json:"route"`
	Drive     DriveConfig  `json:"drive"`
	Sheets    SheetsConfig `json:"sheets"`
	Tunnel    TunnelConfig `json:"tunnel"`
}

type AuthConfig struct {
	AccessToken  string `json:"access_token,omitempty"`
	TokenCommand string `json:"token_command,omitempty"`
}

type RouteConfig struct {
	Mode           string `json:"mode,omitempty"`
	Proxy          string `json:"proxy,omitempty"`
	GoogleIP       string `json:"google_ip,omitempty"`
	TimeoutSeconds int    `json:"timeout_seconds,omitempty"`
}

type DriveConfig struct {
	FolderID string `json:"folder_id,omitempty"`
}

type SheetsConfig struct {
	SpreadsheetID string `json:"spreadsheet_id"`
	Range         string `json:"range,omitempty"`
}

type TunnelConfig struct {
	Listen           string `json:"listen,omitempty"`
	ChunkSize        int    `json:"chunk_size,omitempty"`
	PollIntervalMS   int    `json:"poll_interval_ms,omitempty"`
	CleanupProcessed bool   `json:"cleanup_processed,omitempty"`
}

func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	cfg.ApplyDefaults()
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return &cfg, nil
}

func (c *Config) ApplyDefaults() {
	if c.Route.Mode == "" {
		c.Route.Mode = "real_pinned"
	}
	if c.Route.GoogleIP == "" {
		c.Route.GoogleIP = "216.239.38.120"
	}
	if c.Route.TimeoutSeconds == 0 {
		c.Route.TimeoutSeconds = 240
	}
	if c.Auth.TokenCommand == "" {
		c.Auth.TokenCommand = "gcloud auth print-access-token"
	}
	if c.Sheets.Range == "" {
		c.Sheets.Range = "skirk!A:D"
	}
	if c.Tunnel.Listen == "" {
		c.Tunnel.Listen = "127.0.0.1:18080"
	}
	if c.Tunnel.ChunkSize == 0 {
		c.Tunnel.ChunkSize = 8192
	}
	if c.Tunnel.PollIntervalMS == 0 {
		c.Tunnel.PollIntervalMS = 1200
	}
}

func (c *Config) Validate() error {
	if strings.TrimSpace(c.Secret) == "" {
		return errors.New("config.secret is required")
	}
	if c.Tunnel.ChunkSize < 512 || c.Tunnel.ChunkSize > 256*1024 {
		return fmt.Errorf("config.tunnel.chunk_size must be between 512 and 262144 bytes")
	}
	return nil
}

func (a AuthConfig) Token(ctx context.Context) (string, error) {
	if token := strings.TrimSpace(os.Getenv("SKIRK_ACCESS_TOKEN")); token != "" {
		return token, nil
	}
	if token := strings.TrimSpace(a.AccessToken); token != "" {
		return token, nil
	}
	command := strings.TrimSpace(a.TokenCommand)
	if command == "" {
		return "", errors.New("no access token or token_command configured")
	}
	ctx, cancel := context.WithTimeout(ctx, 45*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "/bin/sh", "-lc", command)
	path := os.Getenv("PATH")
	home := os.Getenv("HOME")
	if home != "" {
		path = home + "/google-cloud-sdk/bin:" + path
	}
	cmd.Env = append(os.Environ(), "PATH="+path)
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("token command failed: %w", err)
	}
	token := strings.TrimSpace(string(out))
	if token == "" {
		return "", errors.New("token command returned an empty token")
	}
	return token, nil
}

func (c Config) PollInterval() time.Duration {
	return time.Duration(c.Tunnel.PollIntervalMS) * time.Millisecond
}
