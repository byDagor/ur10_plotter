import FreeSimpleGUI as sg
import vpype
from vpype_cli import execute
import time
import traceback
import multiprocessing
import tempfile
import os

def _vectorize_task(cmd_string: str, result_queue: multiprocessing.Queue):
    """
    The actual vectorization task that runs in a separate process.
    The result (a path to a temporary file) is put into a queue.
    """
    try:
        # This is the long-running, blocking call
        document = execute(cmd_string)
        
        if document:
            # Save the document to a temporary file
            fd, temp_path = tempfile.mkstemp(suffix=".svg")
            os.close(fd) # close the file descriptor
            with open(temp_path, "w", encoding="utf-8") as f:
                vpype.write_svg(f, document)
            result_queue.put((True, temp_path))
        else:
            result_queue.put((False, "Vectorization resulted in an empty document."))
            
    except Exception as e:
        result_queue.put((False, str(e)))


def run_vectorize_thread(window: sg.Window, cmd_string: str, is_cmyk: bool, stop_event: "threading.Event"):
    """
    This function runs in a thread and manages a separate process for the
    actual vectorization work. This allows the work to be terminated.
    """
    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_vectorize_task,
        args=(cmd_string, result_queue)
    )

    try:
        window.write_event_value("-LOG_MESSAGE-", "Starting Flow Imager vectorization process...")
        print(f"Running command in separate process: vpype {cmd_string}")
        start_time = time.time()
        
        process.start()

        # Poll for completion or stop signal
        while process.is_alive():
            if stop_event.is_set():
                print("Stop event received, terminating process.")
                process.terminate()
                process.join(timeout=1) # Attempt to gracefully join
                if process.is_alive():
                    print("Process did not terminate, killing.")
                    process.kill() # Force kill if terminate fails
                    process.join() # Wait for the kill
                # The stop event handler in the GUI already takes care of the UI
                return 
            
            time.sleep(0.1)

        # Process finished without being stopped
        end_time = time.time()
        window.write_event_value("-LOG_MESSAGE-", f"Flow Imager process complete in {end_time - start_time:.2f} seconds.")

        # Get the result from the queue
        success, result_path_or_msg = result_queue.get()

        if success:
            temp_path = result_path_or_msg
            window.write_event_value("-LOG_MESSAGE-", "Loading document from temp file...")
            # Use the `execute` function with the 'read' command to load the SVG
            document = execute(f'read "{temp_path}"')
            # Clean up the temporary file
            try:
                os.remove(temp_path)
            except OSError as e:
                print(f"Error removing temp file {temp_path}: {e}")
            
            window.write_event_value("-THREAD_DONE-", (document, "Flow Imager vectorization complete.", is_cmyk))
        else:
            # Handle error from the separate process
            error_message = result_path_or_msg
            print(f"An error occurred in the vectorization process: {error_message}")
            window.write_event_value("-THREAD_DONE-", (None, error_message, False))

    except Exception as e:
        print("An error occurred in the vectorization thread wrapper:")
        traceback.print_exc()
        if process.is_alive():
            process.kill() # Ensure process is killed on wrapper error
            process.join()
        window.write_event_value("-THREAD_DONE-", (None, str(e), False))
    finally:
        # Ensure the queue is closed
        result_queue.close()
        result_queue.join_thread()
