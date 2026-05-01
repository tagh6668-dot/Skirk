package skirk

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"
)

type SheetsLog struct {
	http          *GoogleHTTPClient
	token         string
	spreadsheetID string
	rangeName     string
}

func NewSheetsLog(httpClient *GoogleHTTPClient, token string, cfg SheetsConfig) *SheetsLog {
	rangeName := cfg.Range
	if rangeName == "" {
		rangeName = "skirk!A:D"
	}
	return &SheetsLog{http: httpClient, token: token, spreadsheetID: cfg.SpreadsheetID, rangeName: rangeName}
}

func (s *SheetsLog) Put(ctx context.Context, name string, data []byte) error {
	return s.append(ctx, []string{name, base64.URLEncoding.EncodeToString(data), strconv.FormatInt(time.Now().UnixNano(), 10), "put"})
}

func (s *SheetsLog) Get(ctx context.Context, name string) ([]byte, error) {
	rows, err := s.rows(ctx)
	if err != nil {
		return nil, err
	}
	var latest []string
	for _, row := range rows {
		if len(row) >= 4 && row[0] == name {
			latest = row
		}
	}
	if latest == nil || latest[3] == "delete" {
		return nil, fmt.Errorf("sheet row not found: %s", name)
	}
	return base64.URLEncoding.DecodeString(latest[1])
}

func (s *SheetsLog) List(ctx context.Context, prefix string) ([]ObjectInfo, error) {
	rows, err := s.rows(ctx)
	if err != nil {
		return nil, err
	}
	latest := map[string][]string{}
	for _, row := range rows {
		if len(row) >= 4 && strings.HasPrefix(row[0], prefix) {
			latest[row[0]] = row
		}
	}
	var infos []ObjectInfo
	for name, row := range latest {
		if row[3] == "delete" {
			continue
		}
		infos = append(infos, ObjectInfo{Name: name, Size: int64(len(row[1])), Updated: row[2]})
	}
	sort.Slice(infos, func(i, j int) bool { return infos[i].Name < infos[j].Name })
	return infos, nil
}

func (s *SheetsLog) Delete(ctx context.Context, name string) error {
	return s.append(ctx, []string{name, "", strconv.FormatInt(time.Now().UnixNano(), 10), "delete"})
}

func (s *SheetsLog) append(ctx context.Context, row []string) error {
	encodedRange := url.PathEscape(s.rangeName)
	values := url.Values{}
	values.Set("valueInputOption", "RAW")
	values.Set("insertDataOption", "INSERT_ROWS")
	body, err := json.Marshal(map[string]any{
		"majorDimension": "ROWS",
		"values":         [][]string{row},
	})
	if err != nil {
		return err
	}
	path := fmt.Sprintf("/v4/spreadsheets/%s/values/%s:append?%s", url.PathEscape(s.spreadsheetID), encodedRange, values.Encode())
	result, err := s.http.Request(ctx, http.MethodPost, "sheets.googleapis.com", path, s.jsonHeaders(), body)
	if err != nil {
		return err
	}
	return require2xx(result, "sheets append")
}

func (s *SheetsLog) rows(ctx context.Context) ([][]string, error) {
	encodedRange := url.PathEscape(s.rangeName)
	path := fmt.Sprintf("/v4/spreadsheets/%s/values/%s?majorDimension=ROWS", url.PathEscape(s.spreadsheetID), encodedRange)
	result, err := s.http.Request(ctx, http.MethodGet, "sheets.googleapis.com", path, s.authHeaders(), nil)
	if err != nil {
		return nil, err
	}
	if result.Status == http.StatusNotFound {
		return nil, nil
	}
	if err := require2xx(result, "sheets get"); err != nil {
		return nil, err
	}
	var payload struct {
		Values [][]string `json:"values"`
	}
	if err := json.Unmarshal(result.Body, &payload); err != nil {
		return nil, err
	}
	return payload.Values, nil
}

func (s *SheetsLog) jsonHeaders() map[string]string {
	headers := s.authHeaders()
	headers["Content-Type"] = "application/json"
	return headers
}

func (s *SheetsLog) authHeaders() map[string]string {
	return map[string]string{"Authorization": "Bearer " + s.token}
}
