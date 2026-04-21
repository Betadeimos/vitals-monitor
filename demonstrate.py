import subprocess
import time
import os
import signal

def run_demo():
    print("Starting demonstration...")
    
    # Start the spike simulator
    simulator = subprocess.Popen([os.sys.executable, "-u", "demo_spike.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"Simulator started (PID: {simulator.pid})")
    
    # Give simulator a second to start
    time.sleep(1)
    
    # Start vitals.py and pipe 'Y' to it
    # We use a long timeout to give time for the spike to occur and be detected
    vitals = subprocess.Popen([os.sys.executable, "-u", "vitals.py", "demo_spike.py"], 
                              stdin=subprocess.PIPE, 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.STDOUT, 
                              text=True)
    
    print("Vitals started. Waiting for spike and termination...")
    
    # Send 'Y' to vitals.py stdin after some delay
    # Or just write it now, it will be buffered until input() is called
    vitals.stdin.write("Y\n")
    vitals.stdin.flush()
    
    # Monitor vitals output
    start_time = time.time()
    while time.time() - start_time < 40: # 40 second timeout
        line = vitals.stdout.readline()
        if not line:
            break
        print(f"[VITALS]: {line.strip()}")
        if "terminated." in line:
            print("SUCCESS: Vitals reported process termination.")
            break
        if simulator.poll() is not None:
            print("Simulator process exited.")
            break
            
    # Cleanup
    if simulator.poll() is None:
        print("Terminating simulator...")
        simulator.terminate()
        
    if vitals.poll() is None:
        print("Terminating vitals...")
        vitals.terminate()

if __name__ == "__main__":
    run_demo()
