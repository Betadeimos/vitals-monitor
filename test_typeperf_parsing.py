import subprocess
import os

def test_parsing():
    try:
        cmd = ['typeperf', '-sc', '1', '\\GPU Adapter Memory(*)\\Shared Usage']
        res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
        print("Raw output (repr):")
        print(repr(res))
        
        res_lines = res.strip().split('\n')
        print(f"\nNumber of lines after strip/split: {len(res_lines)}")
        for i, line in enumerate(res_lines):
            print(f"Line {i}: {line}")
            
        if len(res_lines) >= 2:
            # Try to find the data line. Usually it's the last one if we only asked for 1 sample.
            # But the original code used res_lines[2].
            print(f"\nOriginal code would try res_lines[2] if len >= 3.")
            if len(res_lines) >= 3:
                vals = res_lines[2].split(',')
                print(f"res_lines[2] split by comma: {vals}")
            else:
                print("res_lines[2] DOES NOT EXIST (len < 3)")
                
            # Improved logic: the sample data is usually the last line
            data_line = res_lines[-1]
            vals = data_line.split(',')
            print(f"\nLast line split by comma: {vals}")
            
            total_shared_bytes = 0.0
            for v in vals[1:]:
                try:
                    v_clean = v.strip('"')
                    val = float(v_clean)
                    total_shared_bytes += val
                    print(f"Parsed value: {val}")
                except (ValueError, IndexError) as e:
                    print(f"Error parsing value '{v}': {e}")
                    continue
            print(f"\nTotal shared GB: {total_shared_bytes / (1024**3)}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_parsing()
