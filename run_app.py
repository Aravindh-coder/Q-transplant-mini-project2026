"""Q-Transplant v2 Application Launcher."""
import os
import sys
import subprocess
import time

def main():
    print("=" * 65)
    print("🚀 Q-TRANSPLANT v2 — Government Organ Allocation Network Launcher")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(base_dir, "venv", "bin", "python3")
    venv_uvicorn = os.path.join(base_dir, "venv", "bin", "uvicorn")
    # backend/backend is the working directory for uvicorn
    backend_path = os.path.join(base_dir, "backend", "backend")

    # Create venv if missing
    if not os.path.exists(venv_python):
        print("[0/2] Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", os.path.join(base_dir, "venv")], check=True)
        req_file = os.path.join(backend_path, "requirements.txt")
        subprocess.run([venv_python, "-m", "pip", "install", "-r", req_file, "-q"], check=True)
        print("     Dependencies installed.")

    # 1. Run v2 System Verification Tests
    print("\n[1/2] Running System Verification Tests...")
    env = os.environ.copy()
    env["PYTHONPATH"] = backend_path
    test_cmd = [venv_python, os.path.join(base_dir, "test_v2_system.py")]
    res = subprocess.run(test_cmd, env=env)
    if res.returncode != 0:
        print("❌ System tests failed. Aborting startup.")
        sys.exit(1)

    # 2. Start FastAPI Server from backend/backend/ so PUBLIC_DIR resolves correctly
    print("\n[2/2] Starting Q-Transplant v2 Unified Application on http://localhost:8000 ...")
    backend_cmd = [venv_uvicorn, "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    backend_proc = subprocess.Popen(backend_cmd, cwd=backend_path)

    print("\n" + "=" * 65)
    print("🎉 Q-TRANSPLANT v2 IS LIVE!")
    print("► Web Application UI : http://localhost:8000/")
    print("► REST API Docs      : http://localhost:8000/docs")
    print("")
    print("Demo Credentials:")
    print("  Root Organizer : root@qtransplant.gov.in  / root123456")
    print("  AIIMS Hospital : aiims@hospital.org       / hospital123")
    print("  Apollo Hospital: apollo@hospital.org      / hospital123")
    print("=" * 65)
    print("Press Ctrl+C to stop the server.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down Q-Transplant v2 server...")
        backend_proc.terminate()

if __name__ == "__main__":
    main()
