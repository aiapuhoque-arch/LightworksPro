"""
Run this once to add your Microsoft Azure App Client ID to Lightworks Pro.

Usage:
  python scripts\set_microsoft_client_id.py

You will be prompted to paste the Client ID (UUID from the Azure portal).
"""
import json
import os
import sys
from pathlib import Path

appdata = Path(os.environ.get("APPDATA", "")) / "LightworksPro"
config_file = appdata / "config.json"

if not config_file.exists():
    print("Config not found. Launch Lightworks Pro once to create it, then re-run this script.")
    sys.exit(1)

with open(config_file, encoding="utf-8") as f:
    config = json.load(f)

current = config.get("microsoft_client_id", "")
if current:
    print(f"Current Client ID: {current}")
    print("Press Enter to keep it, or paste a new one:")
else:
    print("Paste your Azure App Client ID and press Enter:")

client_id = input().strip()
if not client_id:
    print("No change made.")
    sys.exit(0)

# Basic UUID sanity check
clean = client_id.replace("-", "")
if len(clean) != 32 or not all(c in "0123456789abcdefABCDEF" for c in clean):
    print("That does not look like a valid UUID Client ID. Please try again.")
    sys.exit(1)

config["microsoft_client_id"] = client_id.lower()
config.setdefault("microsoft_tenant_id", "common")

with open(config_file, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)

print(f"\nSaved to {config_file}")
print("Restart Lightworks Pro — it will walk you through signing in to Microsoft 365.")
