import subprocess
import time
import os

def run_demo():
    print("Starting demonstration (Choice: N)...")
    
    # Start the spike simulator
    simulator = subprocess.Popen([os.sys.executable, "-u", "demo_spike.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"Simulator started (PID: {simulator.pid})")
    
    time.sleep(1)
    
    # Start vitals.py and pipe 'N' to it
    vitals = subprocess.Popen([os.sys.executable, "-u", "vitals.py", "demo_spike.py"], 
                              stdin=subprocess.PIPE, 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.STDOUT, 
                              text=True)
    
    print("Vitals started. Waiting for spike...")
    
    # Send 'N' to vitals.py stdin
    vitals.stdin.write("N\n")
    vitals.stdin.flush()
    
    # Monitor vitals output
    start_time = time.time()
    spike_detected = False
    resumed = False
    
    while time.time() - start_time < 30: # 30 second timeout
        line = vitals.stdout.readline()
        if not line:
            break
        print(f"[VITALS]: {line.strip()}")
        if "!!! CRITICAL MEMORY SPIKE DETECTED !!!" in line:
            spike_detected = True
            print("Spike detected!")
        if "Resuming monitoring" in line:
            resumed = True
            print("Monitoring resumed!")
        if resumed and "Status: Normal" in line:
            print("SUCCESS: Vitals resumed normal monitoring after 'N'.")
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
