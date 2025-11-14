import FreeSimpleGUI as sg
from vpype_cli import execute
import time
import traceback

def run_vectorize_thread(window: sg.Window, cmd_string: str, is_cmyk: bool):
    """
    Runs the long 'execute' command in a separate thread and sends an
    event back to the main GUI loop when finished.
    """
    try:
        print(f"Running command: vpype {cmd_string}")
        start_time = time.time()
        document = execute(cmd_string)
        end_time = time.time()
        print(f"Vectorization complete in {end_time - start_time:.2f} seconds.")
        
        # Send an event to the main thread with the result
        window.write_event_value("-THREAD_DONE-", (document, None, is_cmyk))
        
    except Exception as e:
        print("An error occurred in the vectorization thread:")
        traceback.print_exc()
        # Send the error message back
        window.write_event_value("-THREAD_DONE-", (None, str(e), False))
