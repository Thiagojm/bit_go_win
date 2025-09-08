"""Basic randomness tests for BitBabbler output.

This script can read random bytes from:
- A connected BitBabbler device by invoking the Go CLI `bb.exe` and parsing its HEX output
- A file (raw bytes or hex string)

It computes:
- Monobit frequency test (bits)
- Runs test (Wald–Wolfowitz) on bits
- Byte distribution chi-square statistic and p-approximation
- Shannon entropy per byte
- Serial correlation coefficient (bytes)

These are sanity checks, not a substitute for full suites like NIST STS or
Dieharder. For reliable assessment, use larger samples (e.g., multiple MB).
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
from typing import Iterable, List, Optional, Tuple


def run_bb_and_read_hex(bits: int, bb_path: str = "bb.exe", timeout_s: float = 5.0) -> bytes:
    """Run bb.exe with --bits and return the parsed HEX bytes.

    - bits: number of bits to request from bb.exe
    - bb_path: path to bb.exe (default assumes same directory or on PATH)
    - timeout_s: process timeout in seconds
    """
    if bits <= 0:
        raise ValueError("bits must be > 0")

    try:
        proc = subprocess.run(
            [bb_path, "--bits", str(bits)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=True,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"bb.exe timed out after {timeout_s:.1f}s") from e
    except FileNotFoundError as e:
        raise RuntimeError("bb.exe not found; set --bb-path or place it on PATH") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"bb.exe failed: rc={e.returncode}, stderr={e.stderr.strip()}") from e

    hex_line: Optional[str] = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("HEX:"):
            hex_line = line[len("HEX:"):].strip()
            break

    if not hex_line:
        raise RuntimeError("Could not find HEX output in bb.exe stdout")

    # Remove optional spaces, convert to bytes
    hex_str = hex_line.replace(" ", "")
    try:
        data = bytes.fromhex(hex_str)
    except ValueError as e:
        raise RuntimeError(f"Invalid HEX from bb.exe: {hex_str!r}") from e

    # bb.exe masks excess bits in the final byte; length should be ceil(bits/8)
    expected_len = (bits + 7) // 8
    if len(data) != expected_len:
        # If bb.exe decided to return fewer bytes (e.g., leading zeros trimmed), left-pad
        if len(data) < expected_len:
            data = (b"\x00" * (expected_len - len(data))) + data
        else:
            data = data[:expected_len]

    return data


def bits_from_bytes(data: bytes) -> Iterable[int]:
    """Yield bits (MSB first) from a bytes buffer."""
    for b in data:
        for i in range(8):
            yield (b >> (7 - i)) & 1


def monobit_test(data: bytes) -> Tuple[float, float, int, int]:
    """Return (p_value, z, ones, zeros) for monobit frequency test."""
    bs = list(bits_from_bytes(data))
    n = len(bs)
    if n == 0:
        return (0.0, 0.0, 0, 0)
    ones = sum(bs)
    zeros = n - ones
    s = abs(ones - zeros)
    z = s / math.sqrt(n)
    p = math.erfc(z / math.sqrt(2.0))
    return (p, z, ones, zeros)


def runs_test(data: bytes) -> Tuple[float, int, float, float]:
    """Return (p_value, num_runs, expected_runs, z) for bit runs test (Wald–Wolfowitz)."""
    bs = list(bits_from_bytes(data))
    n = len(bs)
    if n < 2:
        return (0.0, 0, 0.0, 0.0)
    ones = sum(bs)
    zeros = n - ones
    if ones == 0 or zeros == 0:
        return (0.0, 1, 0.0, float("inf"))
    runs = 1
    for i in range(1, n):
        if bs[i] != bs[i - 1]:
            runs += 1
    expected = 1 + (2 * ones * zeros) / n
    variance = (2 * ones * zeros * (2 * ones * zeros - n)) / (n ** 2 * (n - 1))
    if variance <= 0:
        return (0.0, runs, expected, float("inf"))
    z = (runs - expected) / math.sqrt(variance)
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return (p, runs, expected, z)


def byte_chi_square(data: bytes) -> Tuple[float, float]:
    """Return (chi_square, p_approx) for byte distribution over 256 bins.

    p_approx uses a normal approximation to the chi-square distribution's CDF
    for df=255; this is rough but indicative. Prefer scipy for exact p.
    """
    n = len(data)
    if n == 0:
        return (0.0, 0.0)
    counts: List[int] = [0] * 256
    for b in data:
        counts[b] += 1
    expected = n / 256.0
    chi = 0.0
    for c in counts:
        diff = c - expected
        chi += (diff * diff) / expected
    df = 255
    c = (chi / df) ** (1.0 / 3.0)
    mu = 1 - 2 / (9 * df)
    sigma = math.sqrt(2 / (9 * df))
    z = (c - mu) / sigma
    p = 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return (chi, p)


def shannon_entropy_per_byte(data: bytes) -> float:
    """Return Shannon entropy (bits per byte)."""
    if not data:
        return 0.0
    counts: List[int] = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    entropy = 0.0
    for c in counts:
        if c == 0:
            continue
        p = c / n
        entropy -= p * math.log2(p)
    return entropy


def serial_correlation(data: bytes) -> float:
    """Return serial correlation coefficient across adjacent bytes (circular)."""
    n = len(data)
    if n < 2:
        return 0.0
    s1 = sum(data)
    s2 = sum(b * b for b in data)
    s12 = sum(data[i] * data[(i + 1) % n] for i in range(n))
    numerator = n * s12 - s1 * s1
    denominator = n * s2 - s1 * s1
    if denominator == 0:
        return 0.0
    return numerator / denominator


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Basic randomness tests for BitBabbler output")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--bb-bits", type=int, help="Read this many bits via bb.exe")
    src.add_argument("--file", help="Read bytes from file instead of device")
    p.add_argument("--bb-path", default="bb.exe", help="Path to bb.exe (default: bb.exe)")
    p.add_argument("--bb-timeout", type=float, default=5.0, help="bb.exe timeout in seconds")
    p.add_argument("--hex", action="store_true", help="Treat file input as hex string instead of raw")
    return p.parse_args()


def main() -> int:
    try:
        args = parse_args()
        if args.file:
            with open(args.file, "rb") as f:
                data = f.read()
            if args.hex:
                data = bytes.fromhex(data.decode().strip())
        else:
            # Read via bb.exe HEX output
            if args.bb_bits is None:
                raise RuntimeError("--bb-bits is required when not using --file")
            data = run_bb_and_read_hex(args.bb_bits, bb_path=args.bb_path, timeout_s=args.bb_timeout)

        if len(data) < 1024:
            print(f"warning: small sample size ({len(data)} bytes); results may be unreliable", file=sys.stderr)

        # Tests
        p_mono, z_mono, ones, zeros = monobit_test(data)
        p_runs, runs, expected_runs, z_runs = runs_test(data)
        chi, p_chi = byte_chi_square(data)
        ent = shannon_entropy_per_byte(data)
        rho = serial_correlation(data)

        # Report
        print("Sample size:", len(data), "bytes")
        print("Shannon entropy:", f"{ent:.5f}", "/ 8.00000 bits/byte")
        print("Serial correlation:", f"{rho:.6f}")
        print()
        print("Monobit frequency:")
        print("  ones:", ones, "zeros:", zeros)
        print("  z:", f"{z_mono:.4f}", "p-value:", f"{p_mono:.6f}")
        print()
        print("Runs test:")
        print("  runs:", runs, "expected:", f"{expected_runs:.2f}")
        print("  z:", f"{z_runs:.4f}", "p-value:", f"{p_runs:.6f}")
        print()
        print("Byte chi-square:")
        print("  chi^2:", f"{chi:.2f}", "df=255", "p~:", f"{p_chi:.6f}")

        return 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

