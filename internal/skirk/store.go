package skirk

import "context"

type ObjectInfo struct {
	Name    string
	ID      string
	Size    int64
	Updated string
}

type BlobStore interface {
	Put(ctx context.Context, name string, data []byte) error
	Get(ctx context.Context, name string) ([]byte, error)
	List(ctx context.Context, prefix string) ([]ObjectInfo, error)
	Delete(ctx context.Context, name string) error
}
