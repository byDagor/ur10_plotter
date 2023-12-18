import rtde_control
import rtde_receive
import frrpc
import time
import copy
import time


from xml.dom import minidom
from svg.path import parse_path


if __name__ == "__main__":

    UR10 = False
    FR5 = True

    DRY_RUN = False

    line_list = []

    if UR10: 
        START_X = -0.100
        START_Y = -1.000
        START_Z =  -0.0
        RX = 3.14
        RY = 0
        RZ = 0

        MAIN = [START_X, START_Y, START_Z, RX, RY, RZ]
        line_list = [[START_X, START_Y, START_Z, RX, RY, RZ],]

    elif FR5: 
        START_X = -100.0
        START_Y = -600.0
        START_Z =  90.0
        RX = 180.0
        RY = 0.0
        RZ = -90.0

        MAIN = [START_X, START_Y, START_Z, RX, RY, RZ]
        line_list = [[START_X, START_Y, START_Z, RX, RY, RZ],]


    if UR10:
        doc = minidom.parse('PINTR(6).svg')
        #doc = minidom.parse('squiggleCam_1696132106938.svg')
        i = 0
        for ipath, path in enumerate(doc.getElementsByTagName('path')):
            i += 1
            print("line", i)
            print('Path', ipath)
            d = path.getAttribute('d')
            parsed = parse_path(d)
            # print('Objects:\n', parsed, '\n' + '-' * 20)
            for obj in parsed:
                #print(type(obj).__name__, ', start/end coords:', ((round(obj.start.real, 3), round(obj.start.imag, 3)), (round(obj.end.real, 3), round(obj.end.imag, 3))))
                if DRY_RUN:
                    line_list.append((START_X-((round(obj.end.real, 3)/9)/1000), START_Y-((round(obj.end.imag, 3)/9)/1000), START_Z, RX, RY, RZ))
                else:
                    line_list.append((START_X-((round(obj.end.real, 3)/9)/1000), START_Y-((round(obj.end.imag, 3)/9)/1000), START_Z-20, RX, RY, RZ))
                #line_list.append((START_X-round(obj.end.real, 3), START_Y-round(obj.end.imag, 3), START_Z, RX, RY, RZ))
            print('-' * 20)
            #print(line_list[0])
            
        doc.unlink()

        rtde_c = rtde_control.RTDEControlInterface("192.168.0.11")
        rtde_r = rtde_receive.RTDEReceiveInterface("192.168.0.11")

        rtde_c.moveL(MAIN)

        for coord in line_list:
            print(coord)
            rtde_c.moveL(coord)

        rtde_c.moveL(MAIN)
    
    elif FR5:
        doc = minidom.parse('PINTR(10).svg')
        #doc = minidom.parse('squiggleCam_1696132106938.svg')
        i = 0
        for ipath, path in enumerate(doc.getElementsByTagName('path')):
            i += 1
            print("line", i)
            print('Path', ipath)
            d = path.getAttribute('d')
            parsed = parse_path(d)
            # print('Objects:\n', parsed, '\n' + '-' * 20)
            for obj in parsed:
                #print(type(obj).__name__, ', start/end coords:', ((round(obj.start.real, 3), round(obj.start.imag, 3)), (round(obj.end.real, 3), round(obj.end.imag, 3))))
                if DRY_RUN:
                    line_list.append((START_X+((round(obj.end.real, 3)/6.5)), START_Y+((round(obj.end.imag, 3)/6.5)), START_Z, RX, RY, RZ))
                else:
                    line_list.append((START_X+((round(obj.end.real, 3)/6.5)), START_Y+((round(obj.end.imag, 3)/6.5)), START_Z-20, RX, RY, RZ))
                #line_list.append((START_X-round(obj.end.real, 3), START_Y-round(obj.end.imag, 3), START_Z, RX, RY, RZ))
            print('-' * 20)
            print(line_list[0])
            
        doc.unlink()

        #print(line_list)

        robot = frrpc.RPC('192.168.58.2')
        #ret = robot.GetActualTCPPose(0)  # Obtain the current tool pose of the robot
        #print(ret)

        robot.MoveCart(MAIN,0,0,75.0,20.0,100.0,200.0,-1)

        for coord in line_list:
            speed = 70.0
            accel = 20.0


            print(coord)
            robot.MoveCart(coord,0,0,speed,accel,100.0,200.0,-1)
            time.sleep(0.35)

        robot.MoveCart(MAIN,0,0,75.0,20.0,100.0,200.0,-1)



        
        

    #cut_cake = [[START_X, START_Y, START_Z, RX, RY, RZ],
    #            [START_X, START_Y, START_Z-0.166, RX, RY, RZ],
    #            [START_X, START_Y+0.15, START_Z-0.166, RX, RY, RZ],
    #            [START_X, START_Y+0.15, START_Z, RX, RY, RZ],
    #            [START_X-0.05, START_Y+0.15, START_Z, RX-0.15, RY+1.0, RZ],
    #            [START_X-0.095, START_Y+0.15, START_Z, RX-0.15, RY+1.0, RZ],
    #            [START_X-0.095, START_Y-0.04, START_Z, RX-0.15, RY+1.0, RZ],
    #            [START_X-0.095, START_Y-0.04, START_Z-0.162, RX-0.15, RY+1.0, RZ],
    #            [START_X-0.23, START_Y+0.15, START_Z-0.162, RX-0.15, RY+1.0, RZ],
    #            [START_X, START_Y+0.15, START_Z, RX, RY, RZ]]



    # GOAL (-0.100, -1.000, -0.400, -3.14, 0, 0)
    # Z offset = 0.400m

    #main = (-0.100, -1.000, -0.000, -3.14, 0, 0)
    #rtde_c = rtde_control.RTDEControlInterface("192.168.0.11")
    #rtde_r = rtde_receive.RTDEReceiveInterface("192.168.0.11")
    #actual_q = rtde_r.getActualTCPPose()    
    #print(actual_q)
    #rtde_c.moveL(main)
    #actual_q = rtde_r.getActualTCPPose()    
    #print(actual_q)
    
    #new_q = copy.deepcopy(actual_q)
    #new_q[0] -= 0.1
    #rtde_c.moveL(main)
    #time.sleep(1)
    #rtde_c.moveL(actual_q)