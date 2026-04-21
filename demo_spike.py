import time
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [3ds Max Simulator] - %(levelname)s - %(message)s',
    stream=sys.stdout
)

def simulate_memory_spike(size_mb=300, duration=10):
    """Artificially spikes memory usage by allocating a large object."""
    logging.info(f"SPIKE: Loading large texture buffer ({size_mb} MB memory spike)...")
    dummy_data = bytearray(size_mb * 1024 * 1024)
    time.sleep(duration)
    del dummy_data 
    logging.info("Memory spike concluded.")

if __name__ == "__main__":
    logging.info("Demo Spike started. Spiking memory in 5 seconds...")
    time.sleep(5)
    size_mb = 500
    logging.info(f"SPIKE: Loading large texture buffer ({size_mb} MB memory spike)...")
    dummy_data = bytearray(size_mb * 1024 * 1024)
    # Touch the memory to ensure it is committed
    for i in range(0, len(dummy_data), 4096):
        dummy_data[i] = 1
    logging.info("Memory spike active.")
    time.sleep(15)
    del dummy_data 
    logging.info("Memory spike concluded.")
