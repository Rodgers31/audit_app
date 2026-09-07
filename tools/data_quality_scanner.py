#!/usr/bin/env python3
"""
Data Quality Scanner
Scans all JSON files for fake/suspicious data patterns
"""

import json
import os
from datetime import datetime


def scan_data_files():
    print("DATA QUALITY SCAN")
    print("=" * 40)

    data_files = [
        "oag_audit_data.json",
        "comprehensive_government_reports.json",
        "comprehensive_cob_reports_database.json",
        "ultimate_etl_results.json",
        "enhanced_county_data.json",  # Already fixed
    ]

    suspicious_files = []
    clean_files = []

    for filename in data_files:
        if os.path.exists(filename):
            try:
                with open(filename, "r") as f:
                    data = json.load(f)

                print(f"\n{filename}:")

                # Check file size
                size = os.path.getsize(filename)
                print(f"   Size: {size:,} bytes")

                # Check for obvious fake patterns
                suspicious_patterns = []

                # Convert to string for pattern matching
                data_str = str(data).lower()

                # Check for unrealistic budget figures
                if "budget" in data_str:
                    if "18000000000" in str(data):  # The fake 18B we found
                        suspicious_patterns.append("Contains fake 18B budget")
                    if "3000" in str(data) and "per_capita" in data_str:
                        suspicious_patterns.append("Uniform 3000 per capita pattern")

                # Check for fake population patterns
                if "population" in data_str:
                    if "906197" in str(data):  # Fake Nairobi population
                        suspicious_patterns.append("Contains fake Nairobi population")

                # Check for uniform execution rates
                if '"75.0"' in str(data) or '"75"' in str(data):
                    count_75 = str(data).count('"75.0"') + str(data).count('"75"')
                    if count_75 > 10:
                        suspicious_patterns.append(
                            f"Suspicious uniform 75% pattern ({count_75} instances)"
                        )

                # Check data structure
                if isinstance(data, dict):
                    keys = list(data.keys())[:5]
                    print(f"   Keys: {keys}")
                elif isinstance(data, list):
                    print(f"   Records: {len(data)}")

                if suspicious_patterns:
                    print(f"   SUSPICIOUS: {suspicious_patterns}")
                    suspicious_files.append((filename, suspicious_patterns))
                else:
                    print(f"   CLEAN")
                    clean_files.append(filename)

            except Exception as e:
                print(f"   ERROR: {str(e)[:100]}")
        else:
            print(f"\n{filename}: Not found")

    print(f"\nSUMMARY:")
    print(f"========")
    print(f"Suspicious files: {len(suspicious_files)}")
    for filename, patterns in suspicious_files:
        print(f"  - {filename}: {patterns}")

    print(f"\nClean files: {len(clean_files)}")
    for filename in clean_files:
        print(f"  - {filename}")

    return suspicious_files, clean_files


if __name__ == "__main__":
    suspicious, clean = scan_data_files()
