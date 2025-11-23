import rtde_control
import rtde_receive
import threading
import numpy as np

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

    def execute_path_realtime(self, paths, home_pose, speed_control, window, dry_run=False):
        """
        Executes a list of paths, allowing for pause and stop.
        :param paths: A list of paths, where each path is a list of poses.
        :param home_pose: The starting and ending pose.
        :param speed_control: A mutable object (e.g., a list) containing the speed value.
        :param window: The PySimpleGUI window object.
        :param dry_run: If True, pen up/down moves are skipped.
        """
        if not self.is_connected:
            print("Not connected to the robot.")
            return
        
        self.stop_event.clear()
        self.pause_event.clear()
        
        print("Executing path...")
        self.go_home(home_pose)
        safe_z = home_pose[2] + 0.02  # Safe height for pen-up moves

        for path in paths:
            if not path: continue
            if self.stop_event.is_set(): break

            start_pose = path[0]
            # Move to the start of the path with pen up
            if not dry_run:
                start_pose_up = list(start_pose)
                start_pose_up[2] = safe_z
                self.move_to(start_pose_up, speed=speed_control[0])

            # Move to the start point (pen down if not dry run)
            self.move_to(start_pose, speed=speed_control[0])
            
            # Draw the path
            for i in range(len(path) - 1):
                if self.stop_event.is_set(): break
                
                # --- Pause Logic ---
                if self.pause_event.is_set():
                    print("Path execution paused.")
                    paused_pose = self.get_current_pose()
                    if not dry_run:
                        pen_up_pose = paused_pose.copy()
                        if pen_up_pose[2] < safe_z: # only lift if it's drawing
                            pen_up_pose[2] = safe_z
                            self.move_to(pen_up_pose, speed=0.5)
                    
                    self.pause_event.wait() # Wait for resume
                    print("Resuming path execution.")
                    
                    if not dry_run and paused_pose[2] < safe_z:
                        self.move_to(paused_pose, speed=0.5)
                
                next_pose = path[i+1]
                self.move_to(next_pose, speed=speed_control[0])
                window.write_event_value("-DRAW_LINE-", (path[i], next_pose))

            if self.stop_event.is_set(): break

            # Lift the pen at the end of the path
            end_pose = path[-1]
            if not dry_run:
                end_pose_up = list(end_pose)
                end_pose_up[2] = safe_z
                self.move_to(end_pose_up, speed=speed_control[0])

        self.go_home(home_pose)
        window.write_event_value("-THREAD_DONE-", (None, "Real-time path execution complete.", False))
        print("Path execution complete.")

    def go_home(self, home_pose):
        """
        Moves the robot to the home position (20mm above the canvas).
        """
        if self.is_connected and home_pose:
            safe_home_pose = home_pose.copy()
            safe_home_pose[2] += 0.02  # 20mm higher
            self.move_to(safe_home_pose, speed=0.5)

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
