#!/usr/bin/python 

'''
Author: Avishai Sintov
'''

import rospy
import numpy as np 
from std_msgs.msg import Float64MultiArray, Float32MultiArray, String, Bool, Float32
from std_srvs.srv import Empty, EmptyResponse
from openhand.srv import MoveServos, ReadTemperature
from hand_control.srv import TargetAngles, IsDropped, observation, close, ObjOrientation, CheckOnlineStatus

# from common_msgs_gl.srv import SendDoubleArray, SendBool
import geometry_msgs.msg
import math
import time

class hand_control():

    finger_initial_offset = np.array([0., 0.])
    finger_opening_position = np.array([0., 0.])
    finger_closing_position = np.array([0., 0.])
    finger_move_offset = np.array([0., 0.])
    closed_load = np.array(20.)

    gripper_pos = np.array([0., 0.])
    gripper_load = np.array([0., 0.])
    gripper_temperature = np.array([0., 0.])
    base_rmat = np.zeros(9)
    base_tvec = np.zeros(3)
    obj_pos = np.array([0.,0.,0.])
    obj_height = -1.0e3
    obj_grasped_height = 1.0e3
    gripper_cur_pos = np.array([3.,3.])
    max_load = 280.0

    gripper_status = 'open'
    object_grasped = False
    drop_query = True
    no_detect = True
    no_paral = True
    
    angle = np.array([0.])
    marker0 = np.array([0.,0.,0.])
    marker1 = np.array([0.,0.,0.])
    marker2 = np.array([0.,0.,0.])
    marker3 = np.array([0.,0.,0.])
    cornerPos = np.array([0.,0.,0.])
    
    move_servos_srv = 0.

    def __init__(self):
        rospy.init_node('t42_control', anonymous=True)
        
        if rospy.has_param('~finger_initial_offset'):
            self.finger_initial_offset = rospy.get_param('~finger_initial_offset')
            self.finger_opening_position = rospy.get_param('~finger_opening_position')
            self.finger_closing_position = rospy.get_param('~finger_closing_position')
            self.finger_move_offset = rospy.get_param('~finger_move_offset')
            self.closed_load = rospy.get_param('~finger_close_load')

        rospy.Subscriber('/gripper/pos', Float32MultiArray, self.callbackGripperPos)
        rospy.Subscriber('/gripper/load', Float32MultiArray, self.callbackGripperLoad)
        rospy.Subscriber('/gripper/temperature', Float32MultiArray, self.callbackGripperTemp)
        rospy.Subscriber('/cylinder_pose_incam', geometry_msgs.msg.Pose, self.callbackMarkers)
        rospy.Subscriber('/cylinder_corner_incam',geometry_msgs.msg.Pose,self.callbackCorner)
        rospy.Subscriber('/cylinder_drop', Bool, self.callbackObjectDrop)
        rospy.Subscriber('/finger_markers_incam', geometry_msgs.msg.PoseArray, self.callAddFingerPos)
        rospy.Subscriber('/no_detect', Bool, self.callbackNoDetect)
        rospy.Subscriber('/no_paral', Bool, self.callbackNoParal)
        rospy.Subscriber('/base_rmat', Float32MultiArray, self.callbackBaseRmat)
        rospy.Subscriber('/base_tvec', Float32MultiArray, self.callbackBaseTvec)

        pub_gripper_status = rospy.Publisher('/gripper/gripper_status', String, queue_size=10)
        pub_drop = rospy.Publisher('/hand_control/drop', Bool, queue_size=10)
        pub_obj_pos = rospy.Publisher('/hand_control/obj_pos_incam', Float32MultiArray, queue_size=10)
        #pub_obj_orientation = rospy.Publisher('/object_orientation', Float32MultiArray, queue_size=10)
        
        rospy.Service('/MoveGripperOnline', TargetAngles, self.MoveGripperOnline)
        rospy.Service('/CheckStatusOnline', CheckOnlineStatus, self.CheckStatusOnline)

        rospy.Service('/SlowOpenGripper', Empty, self.SlowOpenGripper)
        rospy.Service('/OpenGripper', Empty, self.OpenGripper)
        rospy.Service('/CloseGripper', close, self.CloseGripper)
        rospy.Service('/MoveGripper', TargetAngles, self.MoveGripper)
        rospy.Service('/IsObjDropped', IsDropped, self.CheckDroppedSrv)
        rospy.Service('/observation', observation, self.GetObservation)

        self.move_servos_srv = rospy.ServiceProxy('/MoveServos', MoveServos)
        self.temperature_srv = rospy.ServiceProxy('/ReadTemperature', ReadTemperature)

        msg = Float32MultiArray()

        self.rate = rospy.Rate(100)
        c = True
        count = 0
        while not rospy.is_shutdown():
            pub_gripper_status.publish(self.gripper_status)

            msg.data = self.obj_pos
            pub_obj_pos.publish(msg)

            #msg.data = self.angle
            #pub_obj_orientation.publish(msg)

            if count > 1000:
                dr, verbose = self.CheckDropped()
                pub_drop.publish(dr)
            count += 1

            if c and not np.all(self.gripper_load==0): # Wait till openhand services ready and set gripper open pose
                self.moveGripper(self.finger_opening_position)
                c = False

            self.rate.sleep()
    
    def callbackCorner(self,msg):
        self.cornerPos = [msg.position.x, msg.position.y, msg.position.z]
        #arr1 = self.cornerPos
        #arr2 = self.obj_pos
        #self.angle[0] = np.arctan2((arr1[1]-arr2[1]),(arr1[0]-arr2[0]))
        #self.angle = np.array(self.angle)

    def callbackGripperPos(self, msg):
        self.gripper_pos = np.array(msg.data)

    def callbackGripperLoad(self, msg):
        self.gripper_load = np.array(msg.data)
    
    def callbackGripperTemp(self, msg):
        self.gripper_temperature = np.array(msg.data)

    def callbackBaseRmat(self,msg):
        self.base_rmat=np.array(msg.data)

    def callbackBaseTvec(self,msg):
        self.base_tvec=np.array(msg.data)

    def callbackMarkers(self, msg):
        self.obj_pos = np.array([msg.position.x, msg.position.y, msg.position.z])
        self.obj_height = msg.position.z

    def callbackObjectDrop(self, msg):
        self.drop_query = msg.data

    def callbackNoDetect(self,msg):
        self.no_detect=msg.data

    def callbackNoParal(self,msg):
        self.no_paral=msg.data

    def callAddFingerPos(self, msg):
        tempMarkers =  msg.poses
        
        self.marker0[0] = tempMarkers[0].position.x
        self.marker0[1] = tempMarkers[0].position.y
        self.marker0[2] = tempMarkers[0].position.z

        self.marker1[0] = tempMarkers[1].position.x
        self.marker1[1] = tempMarkers[1].position.y
        self.marker1[2] = tempMarkers[1].position.z

        self.marker2[0] = tempMarkers[2].position.x
        self.marker2[1] = tempMarkers[2].position.y
        self.marker2[2] = tempMarkers[2].position.z

        self.marker3[0] = tempMarkers[3].position.x
        self.marker3[1] = tempMarkers[3].position.y
        self.marker3[2] = tempMarkers[3].position.z

    def SlowOpenGripper(self,msg):
        print "Opening slowly."
        for _ in range(5):
            desired=self.gripper_pos -np.array([ a/7 for a in self.finger_move_offset])
            self.moveGripper(desired)
            rospy.sleep(0.1)
        self.moveGripper(self.finger_opening_position, open=True)
        self.gripper_status = 'open'
        return EmptyResponse()

    def OpenGripper(self, msg):
        self.moveGripper(self.finger_opening_position, open=True)

        self.gripper_status = 'open'

        return EmptyResponse()

    def CloseGripper(self, msg):
        if np.any(self.gripper_temperature > 52.):
            rospy.logerr('[hand_control] Actuators overheated, taking a break...')
            # rospy.signal_shutdown('[hand_control] Actuators overheated, shutting down. Disconnect power cord!')
            while 1:
                if np.all(self.gripper_temperature < 60.):
                    break
                # rospy.sleep(60*2)
                self.rate.sleep()


        closed_load = self.closed_load#np.random.randint(70, self.closed_load+30) # !!!!!! Remember to change

        self.object_grasped = False
        for i in range(100):
            # print('Angles: ' + str(self.gripper_pos) + ', load: ' + str(self.gripper_load), self.closed_load)
            if abs(self.gripper_load[0]) > closed_load or abs(self.gripper_load[1]) > closed_load:
                rospy.loginfo('[hand] Object grasped.')
                self.gripper_status = 'closed'
                break

            desired = self.gripper_pos + np.array([ a/16 for a in self.finger_move_offset]) #self.finger_move_offset/2.0
            if desired[0] > 0.7 or desired[1] > 0.7:
                rospy.logerr('[hand] Desired angles out of bounds.')
                break
            # print self.gripper_pos, desired
            self.moveGripper(desired)
            rospy.sleep(0.2)  

        self.rate.sleep()

        ## Verify based on gripper motor angles
        print('[hand] Gripper actuator angles: ' + str(self.gripper_pos))
        # if self.gripper_pos[0] < 0.357 and self.gripper_pos[1] < 0.377:
        self.object_grasped = True
        #self.allow_motion_srv(True)
        self.obj_grasped_height = self.obj_height # This will have to be defined in hand base pose

        self.rate.sleep()
        self.gripper_cur_pos = self.gripper_pos
        self.drop_query = True
        #self.drop_query=False

        return {'success': self.object_grasped}


    def MoveGripper(self, msg):
        # This function should accept a vector of normalized incraments to the current angles: msg.angles = [dq1, dq2], where dq1 and dq2 can be equal to 0 (no move), 1,-1 (increase or decrease angles by finger_move_offset)
        f = 100.0

        inc = np.array(msg.angles)
        inc_angles = np.multiply(self.finger_move_offset, inc)
        if (self.gripper_cur_pos!=np.array([3.,3.])).all():
            self.gripper_cur_pos+=inc_angles*1.0/f
            suc=self.moveGripper(self.gripper_cur_pos)
        else:
            desired = self.gripper_pos+inc_angles*1.0/f
            suc = self.moveGripper(desired)

        return {'success': suc}
    
    def moveGripper(self, angles, open=False):
        if not open:
            if angles[0] > 0.9 or angles[1] > 0.9 or angles[0] < 0.02 or angles[1] < 0.02:
                rospy.logerr('[hand] Move Failed. Desired angles out of bounds.')
                return False

            if abs(self.gripper_load[0]) > self.max_load or abs(self.gripper_load[1]) > self.max_load:
                rospy.logerr('[hand] Move failed. Pre-overload.')
                return False

        self.move_servos_srv.call(angles)

        return True

    def MoveGripperOnline(self, msg):
        f = 100.0
        inc = np.array(msg.angles)
        inc_angles = np.multiply(self.finger_move_offset, inc)
        if (self.gripper_cur_pos!=np.array([3.,3.])).all():
            self.gripper_cur_pos+=inc_angles*1.0/f
            self.move_servos_srv.call(self.gripper_cur_pos)
        else:
            desired = self.gripper_pos+inc_angles*1.0/f
            self.move_servos_srv.call(desired)
        return {'success': True}


    def CheckStatusOnline(self,msg):
        obs = np.concatenate((self.base_rmat,self.base_tvec,self.obj_pos, self.cornerPos,self.marker0,self.marker1,self.marker2,self.marker3, self.gripper_load, np.array([float(self.no_detect)]),np.array([float(self.no_paral)]),np.array([float(self.drop_query)]))) 

        suc=True
        try:
            if self.gripper_pos[0] > 0.9 or self.gripper_pos[1] > 0.9 or self.gripper_pos[0] < 0.03 or self.gripper_pos[1] < 0.03:
                rospy.logerr('[hand] Desired angles out of bounds.')
                suc=False
        except:
            print('[hand] Error with gripper_pos.')
            suc=False
        if suc:
            try:
                if abs(self.gripper_load[0]) > self.max_load or abs(self.gripper_load[1]) > self.max_load:
                    rospy.logerr('[hand] Gripper overload.')
                    suc=False
            except:
                print('[hand] Error with gripper_load.')
                suc=False

        if self.drop_query or self.no_detect or self.no_paral:
            rospy.logerr('[hand] Object dropped or Marker not detected or Z axes not parallel.')
            detect_and_no_drop=False
        else:
            detect_and_no_drop=True
        return {'state': obs, 'success': suc, 'grasped': detect_and_no_drop}


    def CheckDropped(self):
        # Should spin (update topics) between moveGripper and this
        if self.drop_query:
            verbose = '[hand] Object dropped.'
            return True, verbose
        if self.no_detect:
            verbose = '[hand] Marker not detected.'
            return True, verbose
        if self.no_paral:
            verbose = '[hand] Z axes not parallel.'
            return True, verbose

        try:
            if self.gripper_pos[0] > 0.9 or self.gripper_pos[1] > 0.9 or self.gripper_pos[0] < 0.03 or self.gripper_pos[1] < 0.03:
                verbose = '[hand] Desired angles out of bounds.'
                return True, verbose
        except:
            print('[hand] Error with gripper_pos.')
            return True, ''

        # Check load
        try:
            if abs(self.gripper_load[0]) > self.max_load or abs(self.gripper_load[1]) > self.max_load:
                verbose = '[hand] Pre-overload.'
                return True, verbose
        except:
            print('[hand] Error with gripper_load.')
            return True, ''

        # If object marker not visible, loop to verify and declare dropped.
        if self.obj_height == -1000:
            dr = True
            for _ in range(25):
                # print('self.obj_height is ', self.obj_height)
                if self.obj_height != -1000:
                    dr = False
                    break
                time.sleep(0.1)
            if dr:
                verbose = '[hand] Object not visible - assumed dropped.'
                return True, verbose
        
        return False, ''

    def CheckDroppedSrv(self, msg):

        dr, verbose = self.CheckDropped()
        
        if len(verbose) > 0:
            rospy.logerr(verbose)

        return {'dropped': dr}


    def GetObservation(self, msg):
        obs = np.concatenate((self.base_rmat,self.base_tvec,self.obj_pos, self.cornerPos,self.marker0,self.marker1,self.marker2,self.marker3, self.gripper_load, np.array([float(self.no_detect)]),np.array([float(self.no_paral)]),np.array([float(self.drop_query)]))) 
        return {'state': obs}



if __name__ == '__main__':
    
    try:
        hand_control()
    except rospy.ROSInterruptException:
        pass
