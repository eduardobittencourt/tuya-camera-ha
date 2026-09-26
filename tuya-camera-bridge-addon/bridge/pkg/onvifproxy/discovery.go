package onvifproxy

import (
	"context"
	"encoding/xml"
	"errors"
	"fmt"
	"net"
	"regexp"
	"strings"
	"sync"
	"time"
)

const discoveryAddress = "239.255.255.250:3702"

var messageIDPattern = regexp.MustCompile(`(?s)<(?:[A-Za-z0-9_]+:)?MessageID[^>]*>\s*(?:urn:)?uuid:([^<]+)</`)

type discoveryResponder struct {
	endpoint string
	scopes   []string
	port     int
	iface    string
	mu       sync.Mutex
	conn     *net.UDPConn
	done     chan struct{}
}

func newDiscoveryResponder(endpoint string, scopes []string, port int, iface string) *discoveryResponder {
	return &discoveryResponder{endpoint: endpoint, scopes: scopes, port: port, iface: iface, done: make(chan struct{})}
}

func (r *discoveryResponder) Start(ctx context.Context) error {
	group, err := net.ResolveUDPAddr("udp4", discoveryAddress)
	if err != nil {
		return err
	}
	var iface *net.Interface
	if r.iface != "" {
		iface, err = net.InterfaceByName(r.iface)
		if err != nil {
			return fmt.Errorf("resolve multicast interface %s: %w", r.iface, err)
		}
	}
	conn, err := net.ListenMulticastUDP("udp4", iface, group)
	if err != nil {
		return fmt.Errorf("listen for WS-Discovery: %w", err)
	}
	r.mu.Lock()
	r.conn = conn
	r.mu.Unlock()
	go r.loop(ctx, conn)
	return nil
}

func (r *discoveryResponder) loop(ctx context.Context, conn *net.UDPConn) {
	defer close(r.done)
	defer conn.Close()
	buffer := make([]byte, 64*1024)
	for {
		_ = conn.SetReadDeadline(time.Now().Add(time.Second))
		n, peer, err := conn.ReadFromUDP(buffer)
		if err != nil {
			var networkError net.Error
			if errors.As(err, &networkError) && networkError.Timeout() {
				select {
				case <-ctx.Done():
					return
				default:
					continue
				}
			}
			return
		}
		request := string(buffer[:n])
		if !strings.Contains(request, "Probe") {
			continue
		}
		match := messageIDPattern.FindStringSubmatch(request)
		if len(match) != 2 {
			continue
		}
		host := localAddressFor(peer.IP.String())
		response := r.probeMatch(match[1], host)
		_, _ = conn.WriteToUDP([]byte(response), peer)
	}
}

func (r *discoveryResponder) Stop() {
	r.mu.Lock()
	conn := r.conn
	r.mu.Unlock()
	if conn != nil {
		_ = conn.Close()
	}
}

func (r *discoveryResponder) probeMatch(relatesTo, host string) string {
	xaddr := fmt.Sprintf("http://%s:%d/onvif/device_service", host, r.port)
	return `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dn="http://www.onvif.org/ver10/network/wsdl" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
<s:Header><a:Action s:mustUnderstand="1">http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</a:Action><a:MessageID>uuid:` + stableUUID(r.endpoint+relatesTo) + `</a:MessageID><a:RelatesTo>uuid:` + xmlEscape(relatesTo) + `</a:RelatesTo><a:To s:mustUnderstand="1">http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:To></s:Header>
<s:Body><d:ProbeMatches><d:ProbeMatch><a:EndpointReference><a:Address>` + xmlEscape(r.endpoint) + `</a:Address></a:EndpointReference><d:Types>dn:NetworkVideoTransmitter tds:Device</d:Types><d:Scopes>` + xmlEscape(strings.Join(r.scopes, " ")) + `</d:Scopes><d:XAddrs>` + xmlEscape(xaddr) + `</d:XAddrs><d:MetadataVersion>1</d:MetadataVersion></d:ProbeMatch></d:ProbeMatches></s:Body></s:Envelope>`
}

func xmlEscape(value string) string {
	var b strings.Builder
	_ = xml.EscapeText(&b, []byte(value))
	return b.String()
}

func localAddressFor(peer string) string {
	connection, err := net.Dial("udp4", net.JoinHostPort(peer, "3702"))
	if err != nil {
		return "127.0.0.1"
	}
	defer connection.Close()
	host, _, err := net.SplitHostPort(connection.LocalAddr().String())
	if err != nil {
		return "127.0.0.1"
	}
	return host
}
