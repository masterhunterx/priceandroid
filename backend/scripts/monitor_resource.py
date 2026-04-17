import psutil
import time
import os
import sys

def get_backend_process():
    """Find the uvicorn/python process running the backend."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and 'api.main' in ' '.join(cmdline):
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def monitor(interval=1):
    print("[MONITOR] Iniciando monitoreo de recursos para Stress Test...")
    print("Esperando a que el backend se inicie (api.main)...")
    
    backend_proc = None
    while not backend_proc:
        backend_proc = get_backend_process()
        if not backend_proc:
            time.sleep(1)
    
    print(f"[MONITOR] Backend detectado (PID: {backend_proc.pid})")
    print(f"{'Time':<10} | {'CPU %':<8} | {'Mem MB':<10} | {'Threads':<8}")
    print("-" * 45)

    try:
        while True:
            if not backend_proc.is_running():
                print("\n❌ [MONITOR] El proceso del backend se ha detenido.")
                break
                
            cpu = backend_proc.cpu_percent(interval=None)
            mem = backend_proc.memory_info().rss / (1024 * 1024)
            threads = backend_proc.num_threads()
            
            curr_time = time.strftime("%H:%M:%S")
            print(f"{curr_time:<10} | {cpu:<8.1f} | {mem:<10.1f} | {threads:<8}")
            
            # Check for generic system saturation
            if psutil.cpu_percent() > 95:
                print("⚠️  [ALERTA] CPU del sistema saturado (>95%)")
                
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n🛑 [MONITOR] Detenido por el usuario.")

if __name__ == "__main__":
    monitor()
