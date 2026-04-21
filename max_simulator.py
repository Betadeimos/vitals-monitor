import time
import random
import math
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [3ds Max Simulator] - %(levelname)s - %(message)s',
    stream=sys.stdout
)

def heavy_calculation(ram_mb=200, duration=5):
    """
    Simulates a complex task:
    - Spikes CPU usage.
    - Allocates RAM for the duration.
    - Releases RAM and returns to idle.
    """
    logging.info(f"[BUSY] Performing heavy calculation... Allocating {ram_mb}MB for {duration}s.")
    
    # Allocate memory
    data = bytearray(ram_mb * 1024 * 1024)
    
    end_time = time.time() + duration
    # Spike CPU by doing calculations for the duration
    while time.time() < end_time:
        # Busy loop for CPU usage
        # We use a small range to allow time.time() checks
        for _ in range(10000):
            _ = math.sqrt(random.random() * 10.0)
    
    del data # Release RAM
    logging.info("Heavy calculation concluded.")

# Persistent storage for the leak
_leak_data = []

def fatal_memory_leak(chunk_mb=50, interval=1, iterations=None):
    """
    Simulates a fatal memory leak:
    - Continuously allocates RAM in small chunks.
    - Never releases it.
    - 'iterations' parameter is used for testing purposes.
    """
    logging.info("[CRITICAL] Memory leak initiated!")
    
    count = 0
    while True:
        if iterations is not None and count >= iterations:
            break
            
        logging.info(f"Allocating {chunk_mb}MB... Total leak approximately {(len(_leak_data) + 1) * chunk_mb}MB")
        _leak_data.append(bytearray(chunk_mb * 1024 * 1024))
        
        time.sleep(interval)
        count += 1

def run_simulation():
    """Main loop for the 3ds Max simulator."""
    logging.info("3ds Max Simulation started. Press Ctrl+C to stop.")
    
    try:
        while True:
            # Randomly decide behavior
            # We include 'idle' multiple times to favor it
            behavior = random.choice(['heavy', 'leak', 'idle', 'idle', 'idle'])
            
            if behavior == 'heavy':
                heavy_calculation(ram_mb=200, duration=5)
            elif behavior == 'leak':
                # Warning: leak won't return until completion or error if it was a loop,
                # but here fatal_memory_leak is infinite unless iterations are set.
                fatal_memory_leak(chunk_mb=50, interval=1)
                # If leak returns (e.g. error), we'd continue, but it's infinite.
            else:
                logging.info("[IDLE] Status: Normal operations...")
                time.sleep(random.uniform(2, 5))
            
    except KeyboardInterrupt:
        logging.info("3ds Max Simulation stopped by user.")

if __name__ == "__main__":
    run_simulation()
