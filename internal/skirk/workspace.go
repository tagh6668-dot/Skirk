package skirk

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
)

type Workspace struct {
	http  *GoogleHTTPClient
	token string
}

func NewWorkspace(httpClient *GoogleHTTPClient, token string) *Workspace {
	return &Workspace{http: httpClient, token: token}
}

func (w *Workspace) CreateSpreadsheet(ctx context.Context, title, sheetTitle string) (string, error) {
	if title == "" {
		title = "skirk-workspace"
	}
	if sheetTitle == "" {
		sheetTitle = "skirk"
	}
	body, err := json.Marshal(map[string]any{
		"properties": map[string]string{"title": title},
		"sheets": []map[string]any{
			{"properties": map[string]string{"title": sheetTitle}},
		},
	})
	if err != nil {
		return "", err
	}
	result, err := w.http.Request(ctx, http.MethodPost, "sheets.googleapis.com", "/v4/spreadsheets", w.jsonHeaders(), body)
	if err != nil {
		return "", err
	}
	if err := require2xx(result, "sheets create"); err != nil {
		return "", err
	}
	var payload struct {
		SpreadsheetID string `json:"spreadsheetId"`
	}
	if err := json.Unmarshal(result.Body, &payload); err != nil {
		return "", err
	}
	if payload.SpreadsheetID == "" {
		return "", fmt.Errorf("sheets create response did not include spreadsheetId")
	}
	return payload.SpreadsheetID, nil
}

func (w *Workspace) DeleteSpreadsheet(ctx context.Context, spreadsheetID string) error {
	result, err := w.http.Request(ctx, http.MethodDelete, "www.googleapis.com", "/drive/v3/files/"+url.PathEscape(spreadsheetID), w.authHeaders(), nil)
	if err != nil {
		return err
	}
	if result.Status == http.StatusNoContent || result.Status == http.StatusOK || result.Status == http.StatusNotFound {
		return nil
	}
	return require2xx(result, "workspace delete")
}

func (w *Workspace) jsonHeaders() map[string]string {
	headers := w.authHeaders()
	headers["Content-Type"] = "application/json"
	return headers
}

func (w *Workspace) authHeaders() map[string]string {
	return map[string]string{"Authorization": "Bearer " + w.token}
}

func StoresFromConfig(ctx context.Context, cfg *Config) (*DriveStore, *SheetsLog, *Workspace, error) {
	token, err := cfg.Auth.Token(ctx)
	if err != nil {
		return nil, nil, nil, err
	}
	httpClient := NewGoogleHTTPClient(cfg.Route)
	drive := NewDriveStore(httpClient, token, cfg.Drive)
	sheets := NewSheetsLog(httpClient, token, cfg.Sheets)
	workspace := NewWorkspace(httpClient, token)
	return drive, sheets, workspace, nil
}
