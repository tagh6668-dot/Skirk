package skirk

import (
	"context"
	"io"
	"net"
	"testing"
	"time"
)

func TestSOCKSClientDialer(t *testing.T) {
	echo, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer echo.Close()
	go func() {
		conn, err := echo.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		_, _ = io.Copy(conn, conn)
	}()

	socks := SOCKSServer{
		Listen: "127.0.0.1:0",
		Handler: func(ctx context.Context, target string, conn net.Conn) {
			remote, err := net.Dial("tcp", target)
			if err != nil {
				return
			}
			defer remote.Close()
			go io.Copy(remote, conn)
			io.Copy(conn, remote)
		},
	}
	listener, err := net.Listen("tcp", socks.Listen)
	if err != nil {
		t.Fatal(err)
	}
	addr := listener.Addr().String()
	listener.Close()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		socks.Listen = addr
		_ = socks.Serve(ctx)
	}()
	time.Sleep(50 * time.Millisecond)

	conn, err := dialViaSOCKS5(context.Background(), "socks5h://"+addr, echo.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	if _, err := conn.Write([]byte("ping")); err != nil {
		t.Fatal(err)
	}
	buf := make([]byte, 4)
	if _, err := io.ReadFull(conn, buf); err != nil {
		t.Fatal(err)
	}
	if string(buf) != "ping" {
		t.Fatalf("got %q", buf)
	}
}
