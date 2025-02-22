#!/usr/bin/env python

import rospy
from std_msgs.msg import String, Float32MultiArray, Bool
from std_srvs.srv import Empty, EmptyResponse, SetBool
from rollout_t42.srv import rolloutReq, rolloutReqFile, plotReq, observation, IsDropped, TargetAngles
from hand_control.srv import RegraspObject, close
import numpy as np
import matplotlib.pyplot as plt
import pickle


class rollout_actor():
    running = False
    action = np.array([0.,0.])
    suc = True
    drop = False

    def __init__(self):
        rospy.init_node('rollout_actor_t42', anonymous=True)

        rospy.Service('/rollout/run_actor', SetBool, self.callbackTrigger)

        self.move_srv = rospy.ServiceProxy('/MoveGripper', TargetAngles)
        obs_srv = rospy.ServiceProxy('/observation', observation)

        rospy.Subscriber('/rollout/action', Float32MultiArray, self.callbackAction)
        rospy.Subscriber('/hand_control/drop', Bool, self.callbackHandDrop)

        fail_pub = rospy.Publisher('/rollout/fail', Bool, queue_size = 10)
        one_fail_pub = rospy.Publisher('/rollout/one_fail', Bool, queue_size = 10)
        #self.running_pub = rospy.Publisher('/rollout_actor/runnning', Bool, queue_size = 10)
        
        print('[rollout_actor] Ready to rollout...')
        #self.running_pub.publish(False)
        count_fail=0

        self.rate = rospy.Rate(2.5) # 15hz
        while not rospy.is_shutdown():
            one_fail_pub.publish(self.drop)
            if self.running:
                self.suc = self.move_srv(self.action).success
                next_state = np.array(obs_srv().state)
                if self.suc:
                    if next_state[-1] or next_state[-2] or next_state[-3]:
                        count_fail+=1
                        if count_fail>=3:
                            fail_pub.publish(True)
                            print("[rollout_actor] Detection or Drop Fail")
                            self.running = False
                            #self.running_pub.publish(False)
                            count_fail=0
                        else:
                            fail_pub.publish(False)
                            #self.running_pub.publish(True)
                    else:
                        fail_pub.publish(False)
                        #self.running_pub.publish(True)
                        count_fail=0
                else:
                    fail_pub.publish(True)
                    print("[rollout_actor] Move Fail")
                    self.running = False
                    #self.running_pub.publish(False)
                    count_fail=0

            self.rate.sleep()

    def callbackAction(self, msg):
        self.action = np.array(msg.data)

    def callbackHandDrop(self, msg):
        self.drop = msg.data

    def callbackTrigger(self, msg):
        self.running = msg.data
        if self.running:
            print("[rollout_actor] Started ...")
            self.suc = True
            #self.running_pub.publish(True)

        return {'success': True, 'message': ''}


if __name__ == '__main__':
    try:
        rollout_actor()
    except rospy.ROSInterruptException:
        pass