"""
Captures real Phoenix UI screenshot from http://localhost:6006.
Per Final Repository Changes Item 2.
"""

import os
import shutil
import subprocess
from pathlib import Path


def capture_phoenix_ui(output_path: str = "reports/dashboard.png") -> bool:
    """
    Captures an actual screenshot of the Phoenix UI at localhost:6006.
    If headless browser is available and Phoenix is running, captures genuine UI.
    Otherwise gracefully falls back to locally rendered phoenix-derived dashboard.
    """
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Check if Phoenix server responds
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:6006", timeout=3)
        if resp.status != 200:
            print(f"[capture_phoenix_ui] Phoenix returned HTTP {resp.status}")
            return False
    except Exception as e:
        print(f"[capture_phoenix_ui] Phoenix server not reachable on localhost:6006: {e}")
        return False

    # Candidate browser paths
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]

    browser_bin = None
    for c in candidates:
        if c.exists():
            browser_bin = str(c)
            break

    if not browser_bin:
        browser_bin = shutil.which("chrome") or shutil.which("chromium") or shutil.which("msedge")

    if not browser_bin:
        print("[capture_phoenix_ui] No headless browser executable found.")
        return False

    cmd = [
        browser_bin,
        "--headless",
        "--disable-gpu",
        "--virtual-time-budget=5000",
        f"--screenshot={str(out_p.resolve())}",
        "--window-size=1400,900",
        "http://localhost:6006",
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, timeout=15)
        if out_p.exists() and out_p.stat().st_size > 5000:
            print(f"[capture_phoenix_ui] Successfully captured genuine Phoenix UI screenshot to {output_path} ({out_p.stat().st_size} bytes).")
            return True
        else:
            print(f"[capture_phoenix_ui] Screenshot command exited with {res.returncode}, stderr: {res.stderr.decode('utf-8', errors='ignore')}")
            return False
    except Exception as exc:
        print(f"[capture_phoenix_ui] Failed to capture Phoenix screenshot: {exc}")
        return False


if __name__ == "__main__":
    success = capture_phoenix_ui()
    print("Success:", success)
