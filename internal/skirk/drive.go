package skirk

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"
)

type DriveStore struct {
	http     *GoogleHTTPClient
	token    string
	folderID string
}

func NewDriveStore(httpClient *GoogleHTTPClient, token string, cfg DriveConfig) *DriveStore {
	return &DriveStore{http: httpClient, token: token, folderID: cfg.FolderID}
}

func (d *DriveStore) Put(ctx context.Context, name string, data []byte) error {
	var body bytes.Buffer
	boundary := fmt.Sprintf("skirk-%d", time.Now().UnixNano())
	writer := multipart.NewWriter(&body)
	if err := writer.SetBoundary(boundary); err != nil {
		return err
	}
	metadata := map[string]any{
		"name":          name,
		"mimeType":      "application/octet-stream",
		"appProperties": map[string]string{"skirkName": name},
	}
	if d.folderID != "" {
		metadata["parents"] = []string{d.folderID}
	}
	metaBytes, err := json.Marshal(metadata)
	if err != nil {
		return err
	}
	metaHeader := textproto.MIMEHeader{}
	metaHeader.Set("Content-Type", "application/json; charset=UTF-8")
	metaPart, err := writer.CreatePart(metaHeader)
	if err != nil {
		return err
	}
	if _, err := metaPart.Write(metaBytes); err != nil {
		return err
	}
	dataHeader := textproto.MIMEHeader{}
	dataHeader.Set("Content-Type", "application/octet-stream")
	dataPart, err := writer.CreatePart(dataHeader)
	if err != nil {
		return err
	}
	if _, err := dataPart.Write(data); err != nil {
		return err
	}
	if err := writer.Close(); err != nil {
		return err
	}
	headers := map[string]string{
		"Authorization": "Bearer " + d.token,
		"Content-Type":  "multipart/related; boundary=" + boundary,
	}
	result, err := d.http.Request(ctx, http.MethodPost, "www.googleapis.com", "/upload/drive/v3/files?uploadType=multipart&fields=id,name,size", headers, body.Bytes())
	if err != nil {
		return err
	}
	return require2xx(result, "drive upload")
}

func (d *DriveStore) Get(ctx context.Context, name string) ([]byte, error) {
	info, err := d.latest(ctx, name)
	if err != nil {
		return nil, err
	}
	path := "/drive/v3/files/" + url.PathEscape(info.ID) + "?alt=media"
	result, err := d.http.Request(ctx, http.MethodGet, "www.googleapis.com", path, d.authHeaders(), nil)
	if err != nil {
		return nil, err
	}
	if err := require2xx(result, "drive download"); err != nil {
		return nil, err
	}
	return result.Body, nil
}

func (d *DriveStore) List(ctx context.Context, prefix string) ([]ObjectInfo, error) {
	values := url.Values{}
	values.Set("q", d.query(prefix, false))
	values.Set("fields", "files(id,name,size,modifiedTime)")
	values.Set("pageSize", "1000")
	result, err := d.http.Request(ctx, http.MethodGet, "www.googleapis.com", "/drive/v3/files?"+values.Encode(), d.authHeaders(), nil)
	if err != nil {
		return nil, err
	}
	if err := require2xx(result, "drive list"); err != nil {
		return nil, err
	}
	var payload struct {
		Files []struct {
			ID           string `json:"id"`
			Name         string `json:"name"`
			Size         string `json:"size"`
			ModifiedTime string `json:"modifiedTime"`
		} `json:"files"`
	}
	if err := json.Unmarshal(result.Body, &payload); err != nil {
		return nil, err
	}
	var infos []ObjectInfo
	for _, item := range payload.Files {
		if !strings.HasPrefix(item.Name, prefix) {
			continue
		}
		size, _ := strconv.ParseInt(item.Size, 10, 64)
		infos = append(infos, ObjectInfo{Name: item.Name, ID: item.ID, Size: size, Updated: item.ModifiedTime})
	}
	sort.Slice(infos, func(i, j int) bool { return infos[i].Name < infos[j].Name })
	return infos, nil
}

func (d *DriveStore) Delete(ctx context.Context, name string) error {
	infos, err := d.listExact(ctx, name)
	if err != nil {
		return err
	}
	for _, info := range infos {
		result, err := d.http.Request(ctx, http.MethodDelete, "www.googleapis.com", "/drive/v3/files/"+url.PathEscape(info.ID), d.authHeaders(), nil)
		if err != nil {
			return err
		}
		if result.Status != http.StatusNoContent && result.Status != http.StatusOK && result.Status != http.StatusNotFound {
			return require2xx(result, "drive delete")
		}
	}
	return nil
}

func (d *DriveStore) latest(ctx context.Context, name string) (ObjectInfo, error) {
	infos, err := d.listExact(ctx, name)
	if err != nil {
		return ObjectInfo{}, err
	}
	if len(infos) == 0 {
		return ObjectInfo{}, fmt.Errorf("drive object not found: %s", name)
	}
	sort.Slice(infos, func(i, j int) bool { return infos[i].Updated > infos[j].Updated })
	return infos[0], nil
}

func (d *DriveStore) listExact(ctx context.Context, name string) ([]ObjectInfo, error) {
	values := url.Values{}
	values.Set("q", d.query(name, true))
	values.Set("fields", "files(id,name,size,modifiedTime)")
	values.Set("orderBy", "modifiedTime desc")
	values.Set("pageSize", "1000")
	result, err := d.http.Request(ctx, http.MethodGet, "www.googleapis.com", "/drive/v3/files?"+values.Encode(), d.authHeaders(), nil)
	if err != nil {
		return nil, err
	}
	if err := require2xx(result, "drive lookup"); err != nil {
		return nil, err
	}
	var payload struct {
		Files []struct {
			ID           string `json:"id"`
			Name         string `json:"name"`
			Size         string `json:"size"`
			ModifiedTime string `json:"modifiedTime"`
		} `json:"files"`
	}
	if err := json.Unmarshal(result.Body, &payload); err != nil {
		return nil, err
	}
	var infos []ObjectInfo
	for _, item := range payload.Files {
		if item.Name != name {
			continue
		}
		size, _ := strconv.ParseInt(item.Size, 10, 64)
		infos = append(infos, ObjectInfo{Name: item.Name, ID: item.ID, Size: size, Updated: item.ModifiedTime})
	}
	return infos, nil
}

func (d *DriveStore) authHeaders() map[string]string {
	return map[string]string{"Authorization": "Bearer " + d.token}
}

func (d *DriveStore) query(value string, exact bool) string {
	clauses := []string{"trashed = false"}
	if d.folderID != "" {
		clauses = append(clauses, fmt.Sprintf("'%s' in parents", escapeDriveQuery(d.folderID)))
	}
	if exact {
		clauses = append(clauses, fmt.Sprintf("name = '%s'", escapeDriveQuery(value)))
	} else {
		clauses = append(clauses, fmt.Sprintf("name contains '%s'", escapeDriveQuery(value)))
	}
	return strings.Join(clauses, " and ")
}

func escapeDriveQuery(value string) string {
	value = strings.ReplaceAll(value, "\\", "\\\\")
	value = strings.ReplaceAll(value, "'", "\\'")
	return value
}
