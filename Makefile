.PHONY: test build

test:
	go test ./...
	pytest -q

build:
	mkdir -p bin
	go build -o bin/skirk ./cmd/skirk

