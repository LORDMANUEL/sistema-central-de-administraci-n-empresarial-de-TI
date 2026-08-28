package identity

import (
	"crypto/x509"
	"errors"
	"fmt"
	"regexp"
	"strings"
)

var uuidPattern = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

type Principal struct {
	TenantID          string
	AssetID           string
	DeviceID          string
	CertificateSerial string
}

func FromCertificate(cert *x509.Certificate) (Principal, error) {
	if cert == nil || cert.SerialNumber == nil || cert.SerialNumber.Sign() <= 0 {
		return Principal{}, errors.New("device certificate is missing a valid serial number")
	}
	if len(cert.URIs) != 1 || cert.URIs[0] == nil {
		return Principal{}, errors.New("device certificate must contain exactly one URI SAN")
	}
	u := cert.URIs[0]
	if u.Scheme != "spiffe" || u.Host != "guardian" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return Principal{}, errors.New("device certificate URI SAN is not a Guardian SPIFFE identity")
	}
	parts := strings.Split(strings.TrimPrefix(u.EscapedPath(), "/"), "/")
	if len(parts) != 6 || parts[0] != "tenant" || parts[2] != "asset" || parts[4] != "device" {
		return Principal{}, errors.New("device certificate URI SAN path is invalid")
	}
	tenantID, assetID, deviceID := parts[1], parts[3], parts[5]
	for name, value := range map[string]string{"tenant_id": tenantID, "asset_id": assetID, "device_id": deviceID} {
		if !uuidPattern.MatchString(value) {
			return Principal{}, fmt.Errorf("%s in device certificate is not a UUID", name)
		}
	}
	return Principal{
		TenantID: tenantID,
		AssetID: assetID,
		DeviceID: deviceID,
		CertificateSerial: strings.ToUpper(cert.SerialNumber.Text(16)),
	}, nil
}
