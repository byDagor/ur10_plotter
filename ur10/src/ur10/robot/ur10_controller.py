import rtde_control
import rtde_receive
import threading
import time

SAFE_Z_OFFSET = 0.01

class UR10Controller:
    def __init__(self, ip_address="10.0.10.208"):
        self.ip_address = ip_address
        self.rtde_c = None
        self.rtde_r = None
        self.is_connected = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()

    def connect(self):
        """
        Connects to the UR10 robot.
        """
        try:
            self.rtde_c = rtde_control.RTDEControlInterface(self.ip_address)
            self.rtde_r = rtde_receive.RTDEReceiveInterface(self.ip_address)
            self.is_connected = True
            print("Successfully connected to the UR10 robot.")
            return True
        except Exception as e:
            print(f"Error connecting to the UR10 robot: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """
        Disconnects from the UR10 robot.
        """
        if self.is_connected:
            self.stop_event.set()
            if self.rtde_c:
                if self.rtde_c.isConnected():
                    self.rtde_c.disconnect()
            if self.rtde_r:
                if self.rtde_r.isConnected():
                    self.rtde_r.disconnect()
            self.is_connected = False
            print("Disconnected from the UR10 robot.")

    def move_to(self, pose, speed=0.25, acceleration=1.2):
        """
        Moves the robot to a specific pose.
        :param pose: A list of 6 values [X, Y, Z, Rx, Ry, Rz].
        :param speed: The speed of the robot in m/s.
        :param acceleration: The acceleration of the robot in m/s^2.
        """
        if not self.is_connected:
            print("Not connected to the robot.")
            return
        try:
            self.rtde_c.moveL(pose, speed, acceleration)
        except Exception as e:
            print(f"Error moving the robot: {e}")

    def execute_path_realtime(self, paths, home_pose, speed_control, acceleration, window, dry_run=False):
        """
        Executes a list of paths, allowing for pause and stop.
        :param paths: A list of paths, where each path is a list of poses.
        :param home_pose: The starting and ending pose.
        :param speed_control: A mutable object (e.g., a list) containing the speed value.
        :param acceleration: The acceleration of the robot.
        :param window: The PySimpleGUI window object.
        :param dry_run: If True, pen up/down moves are skipped.
        """
        if not self.is_connected:
            print("Not connected to the robot.")
            return

        self.stop_event.clear()
        self.pause_event.clear()  # Ensure pause is not active at start

        print("Executing path...")
        self.go_home(home_pose, acceleration=acceleration)
        safe_z = home_pose[2] + SAFE_Z_OFFSET

        path_idx = 0
        while path_idx < len(paths):
            if self.stop_event.is_set():
                break
            path = paths[path_idx]
            if not path:
                path_idx += 1
                continue

            # Move to the start of the path with pen up
            start_pose = path[0]
            if not dry_run:
                start_pose_up = list(start_pose)
                start_pose_up[2] = safe_z
                self.move_to(start_pose_up, speed=speed_control[0], acceleration=acceleration)

            # Move to the start point (pen down)
            self.move_to(start_pose, speed=speed_control[0], acceleration=acceleration)

            point_idx = 0
            while point_idx < len(path) - 1:
                if self.stop_event.is_set():
                    break

                # Draw the line segment
                current_pose = path[point_idx]
                next_pose = path[point_idx + 1]
                self.move_to(next_pose, speed=speed_control[0], acceleration=acceleration)
                window.write_event_value("-DRAW_LINE-", (current_pose, next_pose))

                point_idx += 1

                # --- Stop Logic (checks after a line is completed) ---
                if self.stop_event.is_set():
                    print("Stop command received during drawing. Finishing line, lifting pen, and going home.")
                    
                    # 1. Get current position and lift pen
                    stopped_pose_at_line_end = self.get_current_pose()
                    if not dry_run and stopped_pose_at_line_end:
                        pen_up_pose = list(stopped_pose_at_line_end)
                        pen_up_pose[2] = safe_z
                        self.move_to(pen_up_pose, speed=0.5, acceleration=acceleration)

                    # 2. Go to home position
                    self.go_home(home_pose, speed=0.5, acceleration=acceleration)
                    
                    # 3. Send stopped message and exit thread
                    window.write_event_value("-THREAD_DONE-", (None, "Real-time path execution stopped.", False))
                    print("Path execution stopped by user.")
                    return # Exit the function immediately

                # --- Pause Logic (checks after a line is completed) ---
                if self.pause_event.is_set():
                    print("Pause command received. Finishing line and pausing.")
                    
                    # 1. Get current position and lift pen
                    paused_pose_at_line_end = self.get_current_pose()
                    if not dry_run and paused_pose_at_line_end:
                        pen_up_pose = list(paused_pose_at_line_end)
                        pen_up_pose[2] = safe_z
                        self.move_to(pen_up_pose, speed=0.5, acceleration=acceleration)

                    # 2. Go to home position
                    self.go_home(home_pose, speed=0.5, acceleration=acceleration)

                    # 3. Wait for the resume command (pause_event to be cleared)
                    while self.pause_event.is_set():
                        if self.stop_event.is_set():
                            break
                        time.sleep(0.1)  # Poll to reduce CPU usage

                    # 4. Resume Logic
                    if self.stop_event.is_set():
                        continue # Exit the inner loop to be handled by the outer loop's stop check

                    print("Resume command received. Returning to drawing position.")
                    
                    # Move back to the paused position
                    if paused_pose_at_line_end:
                        # Move to a safe Z height above the resume point
                        safe_resume_pose = list(paused_pose_at_line_end)
                        safe_resume_pose[2] = safe_z
                        self.move_to(safe_resume_pose, speed=0.5, acceleration=acceleration)
                        
                        # Move down to the drawing surface if not a dry run
                        if not dry_run:
                            self.move_to(paused_pose_at_line_end, speed=0.5, acceleration=acceleration)

            if self.stop_event.is_set():
                break

            # Lift the pen at the end of the path segment
            if not dry_run and path:
                end_pose = path[-1]
                end_pose_up = list(end_pose)
                end_pose_up[2] = safe_z
                self.move_to(end_pose_up, speed=speed_control[0], acceleration=acceleration)
            
            path_idx += 1

        # Final actions
        if self.stop_event.is_set():
            print("Stop command received. Lifting pen and going home.")
            current_pose_at_stop = self.get_current_pose()
            # Ensure pen is up before going home
            if not dry_run and current_pose_at_stop:
                safe_z = home_pose[2] + SAFE_Z_OFFSET
                if current_pose_at_stop[2] < safe_z: # Check if pen is down
                    pen_up_pose = list(current_pose_at_stop)
                    pen_up_pose[2] = safe_z
                    self.move_to(pen_up_pose, speed=0.5, acceleration=acceleration)
            
            self.go_home(home_pose, acceleration=acceleration)
            window.write_event_value("-THREAD_DONE-", (None, "Real-time path execution stopped.", False))
            print("Path execution stopped by user.")
        else:
            self.go_home(home_pose, acceleration=acceleration)
            window.write_event_value("-THREAD_DONE-", (None, "Real-time path execution complete.", False))
            print("Path execution complete.")

    def go_home(self, home_pose, speed=0.5, acceleration=1.2):
        """
        Moves the robot to the home position (SAFE_Z_OFFSET above the canvas).
        """
        if self.is_connected and home_pose:
            safe_home_pose = home_pose.copy()
            safe_home_pose[2] += SAFE_Z_OFFSET
            self.move_to(safe_home_pose, speed=speed, acceleration=acceleration)

    def execute_move_sequence(self, poses, speed=0.25, acceleration=1.2):
        """
        Moves the robot through a sequence of poses.
        :param poses: A list of poses for the robot to move to.
        :param speed: The speed of the robot in m/s.
        :param acceleration: The acceleration of the robot.
        """
        if not self.is_connected:
            print("Not connected to the robot.")
            return
        
        print("Executing move sequence...")
        for pose in poses:
            self.move_to(pose, speed=speed, acceleration=acceleration)
        print("Move sequence complete.")

    def get_current_pose(self):
        """
        Returns the current TCP pose of the robot.
        :return: A list of 6 values [X, Y, Z, Rx, Ry, Rz].
        """
        if not self.is_connected:
            print("Not connected to the robot.")
            return None
        try:
            return self.rtde_r.getActualTCPPose()
        except Exception as e:
            print(f"Error getting current pose: {e}")
            return None
