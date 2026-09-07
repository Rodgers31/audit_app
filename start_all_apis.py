#!/usr/bin/env python3
"""
START ALL API ENDPOINTS SCRIPT
==============================

This script starts both API services for the Kenya Audit Transparency Application:
1. Modernized Data-Driven API (Port 8004)
2. Main Backend API (Port 8000)

Usage:
    python start_all_apis.py

Requirements:
    - All API files must be in their respective directories
    - Python environment must be activated
    - All dependencies installed
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


class APILauncher:
    def __init__(self):
        self.project_root = Path(__file__).parent.absolute()
        self.processes = []
        self.apis = [
            {
                "name": "Modernized Data-Driven API",
                "script": "modernized_api.py",
                "directory": "apis",
                "port": 8004,
                "url": "http://localhost:8004",
            },
            {
                "name": "Main Backend API",
                "script": "main.py",
                "directory": "backend",
                "port": 8000,
                "url": "http://localhost:8000",
            },
        ]

    def check_files_exist(self):
        """Check if all required API files exist"""
        print("🔍 Checking API files...")
        missing_files = []

        for api in self.apis:
            file_path = self.project_root / api["directory"] / api["script"]
            if not file_path.exists():
                missing_files.append(str(file_path))
                print(f"❌ Missing: {file_path}")
            else:
                print(f"✅ Found: {file_path}")

        if missing_files:
            print(f"\n❌ ERROR: Missing {len(missing_files)} required files!")
            print("Please ensure all API files are in their correct directories.")
            return False

        print("✅ All API files found!")
        return True

    def start_api(self, api_config):
        """Start a single API service"""
        script_path = self.project_root / api_config["directory"] / api_config["script"]
        working_dir = self.project_root / api_config["directory"]

        print(f"🚀 Starting {api_config['name']}...")
        print(f"   📂 Directory: {working_dir}")
        print(f"   📜 Script: {api_config['script']}")
        print(f"   🌐 URL: {api_config['url']}")

        try:
            # Start the process
            process = subprocess.Popen(
                [sys.executable, api_config["script"]],
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            self.processes.append({"process": process, "config": api_config})

            print(f"✅ {api_config['name']} started (PID: {process.pid})")
            return True

        except Exception as e:
            print(f"❌ Failed to start {api_config['name']}: {e}")
            return False

    def start_all_apis(self):
        """Start all API services"""
        print("🚀 STARTING ALL API ENDPOINTS")
        print("=" * 50)

        if not self.check_files_exist():
            return False

        print(f"\n📍 Project Root: {self.project_root}")
        print(f"🐍 Python Executable: {sys.executable}")
        print()

        success_count = 0
        for api in self.apis:
            if self.start_api(api):
                success_count += 1
                time.sleep(2)  # Give each API time to start
            print()

        if success_count == len(self.apis):
            print("🎉 ALL APIs STARTED SUCCESSFULLY!")
            print("=" * 50)
            print("\n📋 API ENDPOINTS SUMMARY:")
            for api in self.apis:
                print(f"• {api['name']}: {api['url']}")

            print("\n🧪 TESTING ENDPOINTS:")
            print("Test the APIs using:")
            print(
                "1. Postman collection: Kenya_Audit_Transparency_API.postman_collection.json"
            )
            print("2. Browser: Visit the URLs above")
            print("3. curl commands")

            print("\n⚠️  IMPORTANT:")
            print("• Keep this terminal open to maintain all APIs")
            print("• Press Ctrl+C to stop all APIs")
            print("• Check individual API logs if endpoints don't respond")

            return True
        else:
            print(f"❌ Only {success_count}/{len(self.apis)} APIs started successfully")
            return False

    def monitor_processes(self):
        """Monitor all running processes"""
        print("\n👀 Monitoring API processes...")
        print("Press Ctrl+C to stop all APIs")

        try:
            while True:
                time.sleep(5)
                for proc_info in self.processes:
                    process = proc_info["process"]
                    config = proc_info["config"]

                    if process.poll() is not None:
                        print(f"⚠️  {config['name']} stopped unexpectedly!")

                        # Capture error output
                        try:
                            stdout, stderr = process.communicate(timeout=1)
                            if stderr:
                                print(f"❌ Error from {config['name']}:")
                                print(f"   {stderr.strip()}")
                            if stdout:
                                print(f"📝 Output from {config['name']}:")
                                print(f"   {stdout.strip()}")
                        except:
                            pass

                        print(f"🔄 Attempting to restart {config['name']}...")
                        if self.start_api(config):
                            print(f"✅ {config['name']} restarted successfully")
                        else:
                            print(f"❌ Failed to restart {config['name']}")

        except KeyboardInterrupt:
            print("\n🛑 Shutdown signal received...")
            self.cleanup()

    def cleanup(self):
        """Clean up all processes"""
        print("🧹 Cleaning up processes...")

        for proc_info in self.processes:
            process = proc_info["process"]
            config = proc_info["config"]

            if process.poll() is None:  # Process still running
                print(f"🛑 Stopping {config['name']}...")
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    print(f"✅ {config['name']} stopped")
                except subprocess.TimeoutExpired:
                    print(f"⚠️  Force killing {config['name']}...")
                    process.kill()
                    process.wait()
                except Exception as e:
                    print(f"❌ Error stopping {config['name']}: {e}")

        print("✅ All APIs stopped")

    def show_status(self):
        """Show status of all APIs"""
        print("📊 API STATUS")
        print("=" * 20)

        for proc_info in self.processes:
            process = proc_info["process"]
            config = proc_info["config"]

            if process.poll() is None:
                print(f"✅ {config['name']}: Running (PID: {process.pid})")
            else:
                print(f"❌ {config['name']}: Stopped")


def main():
    """Main function"""
    launcher = APILauncher()

    print("🔧 KENYA AUDIT TRANSPARENCY API LAUNCHER")
    print("=" * 45)
    print()

    if launcher.start_all_apis():
        try:
            launcher.monitor_processes()
        except Exception as e:
            print(f"❌ Monitoring error: {e}")
            launcher.cleanup()
    else:
        print("❌ Failed to start all APIs")
        launcher.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()
