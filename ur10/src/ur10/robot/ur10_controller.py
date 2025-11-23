import rtde_control
import rtde_receive
import threading
import numpy as np

class UR10Controller:
    def __init__(self, ip_address="192.168.0.11"):
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

    def execute_path_realtime(self, path, home_pose, speed_control, window):
        """
        Executes a list of poses in real-time, allowing for on-the-fly speed changes.
        :param path: A list of poses.
        :param home_pose: The starting and ending pose.
        :param speed_control: A mutable object (e.g., a list) containing the speed value.
        :param window: The PySimpleGUI window object.
        """
        if not self.is_connected:
            print("Not connected to the robot.")
            return
        
        self.stop_event.clear()
        self.pause_event.clear()
        
        print("Executing real-time path...")
        self.go_home(home_pose)

        for i in range(len(path) - 1):
            if self.stop_event.is_set():
                break

            # --- Pause Logic ---
            if self.pause_event.is_set():
                self.rtde_c.speedStop()
                
                # Get current position and lift the pen
                paused_pose = self.get_current_pose()
                pen_up_pose = paused_pose.copy()
                pen_up_pose[2] += 0.02  # Lift pen by 20mm
                self.move_to(pen_up_pose, speed=0.5)
                
                # Wait until the pause is cleared
                self.pause_event.wait() 
                
                # Move back to the paused position
                self.move_to(paused_pose, speed=0.5)

            start_point = np.array(path[i][:3])
            end_point = np.array(path[i+1][:3])
            
            direction = end_point - start_point
            distance = np.linalg.norm(direction)
            if distance == 0:
                continue
            
            direction_unit = direction / distance
            
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    break

                current_pose_np = np.array(self.get_current_pose()[:3])
                remaining_distance = np.linalg.norm(end_point - current_pose_np)
                
                if remaining_distance < 0.001: # 1mm threshold
                    break
                
                speed = speed_control[0]
                velocity_vector = direction_unit * speed
                
                velocity_command = np.append(velocity_vector, [0, 0, 0])
                
                self.rtde_c.speedL(velocity_command.tolist(), 1.0)
            
            window.write_event_value("-DRAW_LINE-", (path[i], path[i+1]))

        self.rtde_c.speedStop()
        self.go_home(home_pose)
        window.write_event_value("-THREAD_DONE-", (None, "Real-time path execution complete.", False))
        print("Real-time path execution complete.")

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
