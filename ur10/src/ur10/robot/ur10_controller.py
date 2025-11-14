import rtde_control
import rtde_receive
import time

class UR10Controller:
    def __init__(self, ip_address="192.168.0.11"):
        self.ip_address = ip_address
        self.rtde_c = None
        self.rtde_r = None
        self.is_connected = False

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
            self.rtde_c.disconnect()
            self.rtde_r.disconnect()
            self.is_connected = False
            print("Disconnected from the UR10 robot.")

    def move_to(self, pose):
        """
        Moves the robot to a specific pose.
        :param pose: A list of 6 values [X, Y, Z, Rx, Ry, Rz].
        """
        if not self.is_connected:
            print("Not connected to the robot.")
            return
        try:
            self.rtde_c.moveL(pose)
        except Exception as e:
            print(f"Error moving the robot: {e}")

    def execute_path(self, path, home_pose):
        """
        Executes a list of poses.
        :param path: A list of poses.
        :param home_pose: The starting and ending pose.
        """
        if not self.is_connected:
            print("Not connected to the robot.")
            return

        print("Executing path...")
        self.move_to(home_pose)
        for pose in path:
            self.move_to(pose)
            time.sleep(0.1) # Small delay between movements
        self.move_to(home_pose)
        print("Path execution complete.")

    def go_home(self, home_pose):
        """
        Moves the robot to the home position.
        """
        self.move_to(home_pose)
