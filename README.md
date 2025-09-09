# BitBabbler on Windows (Go)

A minimal Go implementation to detect and read random data from BitBabbler devices (FTDI FT232H, VID 0x0403, PID 0x7840) on Windows.

This repo provides:
- A Windows USB detector (SetupAPI) to find BitBabbler devices
- A libusb/gousb-based FTDI MPSSE init and read path mirroring the vendor C++
- CLIs:
  - `bbdetect`: list connected BitBabbler devices
  - `bbread`: quick read test
  - `bb`: unified detect and read N bits with formatted output

## Requirements
- Windows 10/11 (x64)
- Go 1.22+
- libusb runtime present (`libusb-1.0.dll` is included in the repo root)
- Driver: the BitBabbler FTDI interface must use a libusb-compatible driver (WinUSB/libusbK). If Windows binds the default FTDI D2XX driver, switch it using Zadig (`https://zadig.akeo.ie`) to WinUSB (recommended) for the BitBabbler interface.

## Build
From the repository root:

```powershell
# Fetch dependencies
go mod tidy

# Build individual tools
go build -o .\bbdetect.exe .\cmd\bbdetect
go build -o .\bbread.exe   .\cmd\bbread
go build -o .\bb.exe       .\cmd\bb
```

## Usage
### Detect
```powershell
.\bbdetect.exe
```
- Prints found devices (friendly name, device path, and hardware IDs) or a message if none are present.

### Quick read test
```powershell
.\bbread.exe
```
- Opens the device, reads a chunk (default buffer is 4096 bytes) and prints how many bytes were read plus the first 32 bytes in hex.

### Unified CLI (detect + read N bits)
```powershell
# Interactive prompt if --bits is omitted
.\bb.exe

# Non-interactive
.\bb.exe --bits 256

# Optional timeout (default 3s)
.\bb.exe --bits 1024 --timeout 5s
```
Output includes:
- HEX: lowercase hex bytes
- BIN: exactly N bits
- INT: big-endian integer value

## Library (package `bbusb`)
### Detect (SetupAPI)
```go
ok, devices, err := bbusb.IsBitBabblerConnected()
```
- Returns whether any device VID 0x0403 / PID 0x7840 is present, and a slice of `DeviceInfo`:
  - `DevicePath string`
  - `HardwareIDs []string`
  - `FriendlyName string`

### Open and read (libusb/gousb)
```go
sess, err := bbusb.OpenBitBabbler(2_500_000, 1) // bitrate 2.5 MHz, latency 1ms
if err != nil { /* handle */ }
defer sess.Close()

buf := make([]byte, n)
_, err = sess.ReadRandom(context.Background(), buf)
```
- `OpenBitBabbler(bitrate uint, latencyMs uint8)`
  - Initializes the FTDI in MPSSE mode following the vendor sequence: reset, purge, disable special chars, set latency, RTS/CTS flow, bitmode reset→MPSSE, MPSSE config (disable div/3phase/adaptive clocks, set pins, set clock divisor), and performs the AA/AB sync check with a retry.
  - Defaults: 2.5 MHz clock if `bitrate == 0`, 1 ms latency if `latencyMs == 0`.
- `ReadRandom(ctx, buf []byte)`
  - Issues an MPSSE read for `len(buf)` bytes and strips the FTDI 2-byte status from each USB packet, returning pure data bytes.

### GUI-friendly helpers
```go
present, list, err := bbusb.IsPresent()

// One-shot bits (returns exactly N bits, last byte masked)
data, err := bbusb.ReadBitsOnce(ctx, 2048, 2_500_000, 1)

// Periodic collector
ch, err := bbusb.StartBitCollector(ctx, 1024, time.Second, 2_500_000, 1)
for r := range ch {
    if r.Err != nil { /* handle */ }
    _ = r.Data // 1024 bits (128 bytes)
}
```

## Troubleshooting
- "No BitBabbler devices found":
  - Check the USB connection and cable.
  - Confirm the device shows as VID `0403`, PID `7840` in Device Manager.
- `MPSSE sync failed` or read failures:
  - Ensure the BitBabbler interface uses a libusb-compatible driver (WinUSB/libusbK) rather than the FTDI D2XX driver. Use Zadig (`https://zadig.akeo.ie`) to switch drivers if needed.
  - Unplug and replug the device and try again.
- Permissions:
  - Normally not required on Windows with WinUSB, but if other software is claiming the interface, close it.

## Notes
- Vendor IDs: `VID 0x0403 (FTDI)`, `PID 0x7840 (BitBabbler)` as defined in vendor sources.
- The implementation mirrors the vendor C++ init and read paths and aims to be conservative about transfer sizes and status handling.
