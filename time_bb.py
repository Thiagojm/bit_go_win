import subprocess
import sys
import time

def main():
    # Default arguments for bb.exe; can be overridden via sys.argv
    bb_args = ['--bits', '256']  # Example: read 256 bits
    
    # If additional arguments are provided, use them as args for bb.exe
    if len(sys.argv) > 1:
        bb_args = sys.argv[1:]
    
    # Path to bb.exe (adjust if not in current directory)
    bb_exe = 'bb.exe'
    
    try:
        # Start timing
        start_time = time.perf_counter()
        
        # Run bb.exe with the provided arguments
        result = subprocess.run([bb_exe] + bb_args, capture_output=True, text=True, check=True)
        
        # End timing
        end_time = time.perf_counter()
        
        # Calculate execution time in milliseconds
        execution_time_ms = (end_time - start_time) * 1000
        
        # Print the result from bb.exe
        print(result.stdout)
        
        # Print execution time
        print(f"Execution time: {execution_time_ms:.2f} ms")
        
    except subprocess.CalledProcessError as e:
        print(f"Error running bb.exe: {e}")
        print(f"Return code: {e.returncode}")
        if e.stdout:
            print(f"Stdout: {e.stdout}")
        if e.stderr:
            print(f"Stderr: {e.stderr}")
    except FileNotFoundError:
        print("bb.exe not found. Ensure it's in the current directory or provide the full path.")

if __name__ == "__main__":
    main()