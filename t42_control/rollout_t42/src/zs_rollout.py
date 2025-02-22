#!/usr/bin/env python

import rospy
from std_msgs.msg import String, Float32MultiArray, Bool
from std_srvs.srv import Empty, EmptyResponse, SetBool
from rollout_t42.srv import rolloutReq, rolloutReqFile, plotReq, observation, IsDropped, TargetAngles, gets, reset, StepOnlineReq, CheckOnlineStatus
from hand_control.srv import RegraspObject, close
import numpy as np
import matplotlib.pyplot as plt
import pickle, time

class rolloutPublisher():
    fail = False
    #one_fail=False
    S = A = T = []

    def __init__(self):
        rospy.init_node('rollout_t42', anonymous=True)
        self.goals=np.array([[-35, 80],[-10, 100],[50, 100], [75, 80]])
        if rospy.has_param('~ubuntu_cali_path'):
            self.ubuntu_cali_path=rospy.get_param('~ubuntu_cali_path')
            with open(self.ubuntu_cali_path,'rb') as f:
                cali_info=np.array(pickle.load(f))
            self.rmat=cali_info[:9].reshape(3,3)
            self.tvec=cali_info[9:]

        rospy.Service('/rollout/rollout', rolloutReq, self.CallbackRollout)
        rospy.Service('/rollout/rollout_v2', rolloutReq, self.CallbackRolloutV2)
        rospy.Service('/rollout/rollout_from_file', rolloutReqFile, self.CallbackRolloutFile)

        self.action_pub = rospy.Publisher('/rollout/action', Float32MultiArray, queue_size = 10)

        #rospy.Subscriber('/rollout/fail', Bool, self.callbacFail)
        #rospy.Subscriber('/rollout/one_fail', Bool, self.callbacOneFail)

        self.rollout_actor_srv = rospy.ServiceProxy('/rollout/run_actor', SetBool)
        self.drop_srv = rospy.ServiceProxy('/IsObjDropped', IsDropped)
        self.move_srv = rospy.ServiceProxy('/MoveGripper', TargetAngles)
        self.obs_srv = rospy.ServiceProxy('/observation', observation)
        self.open_srv = rospy.ServiceProxy('/OpenGripper', Empty) 
        self.close_srv = rospy.ServiceProxy('/CloseGripper', close) 

        rospy.Service('/rollout/ResetOnline', reset, self.CallbackResetOnline)
        #rospy.Service('/rollout/StepOnline', StepOnlinetReq, self.CallbackStepOnline)
        rospy.Service('/rollout/StepOnlineOneStep', StepOnlinetReq, self.CallbackStepOnlineOneStep)
        self.move_online_srv=rospy.ServiceProxy('/MoveGripperOnline', TargetAngles)
        self.check_srv=rospy.ServiceProxy('/CheckStatusOnline', CheckOnlineStatus)

        self.state_dim = 4
        self.action_dim = 2
        self.stepSize = 1
        print('[rollout] Ready to rollout...')

        self.rate = rospy.Rate(10) # 10hz
        rospy.spin()

    def transform_one_state(self,states):
        states=states.reshape(1,-1)
        transformed_states=np.zeros((states.shape[0],4))
        transformed_states[:,1]=-self.rmat.T.dot((states[:,12:15]-self.tvec).T).T[:,0]
        transformed_states[:,0]=self.rmat.T.dot((states[:,12:15]-self.tvec).T).T[:,1]
        for i in range(2,4):
            transformed_states[:,i]=states[:,i+28]
        transformed_states[:,:2]=transformed_states[:,:2]*1000
        checks=states[:,-3:]
        return transformed_states.reshape(-1,),checks.reshape(-1,)


    def run_rollout_v2(self, A):
        finished=False
        while not finished:
            self.rollout_transition = []
            self.fail = False  

            print("[rollout] Place object and press key...")
            raw_input()
            self.close_srv()
            time.sleep(1.0)
            print('[rollout] Verifying grasp...')
            if self.drop_srv().dropped: # Check if really grasped
                print('[rollout] Grasp failed. Restarting')
                self.slow_open()
                self.open_srv()
                continue

            state = np.array(self.obs_srv().state)
            self.S = []
            self.S.append(np.copy(state))  

            print("[rollout] Rolling-out actions...")
            
            # Publish episode actions
            self.running = True
            success = True
            n = 0
            i = 0
            count_fail=0
            while self.running:
                if n == 0:
                    action = A[i,:]
                    i += 1
                    n = self.stepSize
                n -= 1
                print(i, action, A.shape[0])

                if i % 4 == 1:
                    suc=self.move_srv(action).success

                next_state=np.array(self.obs_srv().state)
                self.S.append(np.copy(next_state))
                self.rollout_transition.append([state,action,next_state, not suc or ((next_state[-1] or next_state[-2] or next_state[-3]) and count_fail>=11)])
                state=np.copy(next_state)
                if not suc:
                    print("[rollout] Move Fail.")
                    success = False
                    count_fail=0
                    break
                else:
                    if next_state[-1] or next_state[-2] or next_state[-3]:
                        count_fail+=1
                        if count_fail>=12:
                            print("[rollout] Detection or Drop Fail.")
                            success = False
                            count_fail=0
                            break
                    else:
                        count_fail=0
                if i == A.shape[0] and n == 0:
                    print("[rollout] Complete.")
                    success = True
                    break
                self.rate.sleep()
            rospy.sleep(1.)
            self.slow_open()
            self.open_srv()
            finished=True

        return success

    def slow_open(self):
        print "Opening slowly."
        for _ in range(30):
            self.move_srv(np.array([-6.,-6.]))
            rospy.sleep(0.1)

    #def callbacFail(self, msg):
    #    self.fail = msg.data
        
    #def callbacOneFail(self, msg):
    #    self.one_fail = msg.data

    def CallbackResetOnline(self, msg):
        self.goal_idx=msg.goal_idx
        self.big_goal_radius=msg.big_goal_radius
        self.goal=self.goals[self.goal_idx]
        self.big_goal_radius=4

        while 1:
            self.open_srv()
            print("[rollout] Place object and press key...")
            raw_input()
            self.close_srv()
            time.sleep(1.0)
            print('[rollout] Verifying grasp...')
            if self.drop_srv().dropped: # Check if really grasped
                print('[rollout] Grasp failed. Restarting')
                self.slow_open()
            else:
                break

        print('[rollout] Grasp succeeded and goal already set...')
        st=self.transform_one_state(np.array(self.obs_srv().state))[0]
        return {'states': st}

    def CallbackStepOnline(self, req):
        S,rwd_history,Done_history=[],[],[]
        suc_history,object_grasped_history,goal_reached_history=[],[],[]
        four_S_history=[],[]
        actions_nom = np.array(req.actions).reshape(-1, self.action_dim)
        #actions_nom = np.clip(actions_nom,np.array([-1,-1]),np.array([1,1]))
        for i in range(actions_nom.shape[0]):
            self.move_online_srv(actions_nom[i])
            four_S=[]
            for j in range(4):
                self.rate.sleep()
                res=self.check_srv()
                #next_state = np.array(self.obs_srv().state)
                next_state = np.array(res.state)
                four_S.append(next_state)
                four_S_history.append(next_state)

            next_state,checks=self.transform_one_state(next_state)
            S.append(next_state)

            #res=self.check_srv()
            suc=res.success
            suc_history.append(int(suc))
            object_grasped=res.grasped
            #object_grasped=any(checks)
            object_grasped_history.append(int(object_grasped))
            goal_reached=False
            if np.linalg.norm(next_state[:2]-self.goal) < self.big_goal_radius:
                print('[rollout] Goal Reached.')
                goal_reached=True
            goal_reached_history.append(int(goal_reached))
            failed = not (suc and object_grasped)
            Done=goal_reached or failed
            Done_history.append(int(Done))
            rwd=-np.linalg.norm(self.goal-next_state[:2])-np.square(actions_nom[i]).sum()
            rwd_history.append(rwd)
            if Done:
                print('Episode Finished')
                self.slow_open()
                break
        return {'states': next_state, 'states_history': np.array(S).reshape((-1,)), 'four_states': four_S.reshape((-1,)), 'four_states_history': four_S_history.reshape((-1,)), 'success': suc, 'success_history': np.array(suc_history), 'grasped': object_grasped, 'grasped_history': np.array(object_grasped_history), 'goal_reach': goal_reached, 'goal_reach_history': np.array(goal_reached_history), 'reward': rwd, 'reward_history': np.array(rwd_history), 'done': Done, 'done_history': np.array(Done_history)}


    def CallbackStepOnlineOneStep(self, req):
        S,rwd_history,Done_history=[],[],[]
        suc_history,object_grasped_history,goal_reached_history=[],[],[]
        four_S_history=[],[]
        actions_nom = np.array(req.actions).reshape(-1, self.action_dim)
        #actions_nom = np.clip(actions_nom,np.array([-1,-1]),np.array([1,1]))
        for i in range(actions_nom.shape[0]):
            self.move_online_srv(actions_nom[i])
            four_S=[]
            for j in range(1):
                self.rate.sleep()
                res=self.check_srv()
                #next_state = np.array(self.obs_srv().state)
                next_state=np.array(res.state)
                four_S.append(next_state)
                four_S_history.append(next_state)

            next_state,checks=self.transform_one_state(next_state)
            S.append(next_state)

            #res=self.check_srv()
            suc=res.success
            suc_history.append(int(suc))
            object_grasped=res.grasped
            #object_grasped=any(checks)
            object_grasped_history.append(int(object_grasped))
            goal_reached=False
            if np.linalg.norm(next_state[:2]-self.goal) < self.big_goal_radius:
                print('[rollout] Goal Reached.')
                goal_reached=True
            goal_reached_history.append(int(goal_reached))
            failed = not (suc and object_grasped)
            Done=goal_reached or failed
            Done_history.append(int(Done))
            rwd=-np.linalg.norm(self.goal-next_state[:2])-np.square(actions_nom[i]).sum()
            rwd_history.append(rwd)
            if Done:
                print('Episode Finished')
                self.slow_open()
                break
        return {'states': next_state, 'states_history': np.array(S).reshape((-1,)), 'four_states': four_S.reshape((-1,)), 'four_states_history': four_S_history.reshape((-1,)), 'success': suc, 'success_history': np.array(suc_history), 'grasped': object_grasped, 'grasped_history': np.array(object_grasped_history), 'goal_reach': goal_reached, 'goal_reach_history': np.array(goal_reached_history), 'reward': rwd, 'reward_history': np.array(rwd_history), 'done': Done, 'done_history': np.array(Done_history)}

    def CallbackRollout(self, req):
        print('[rollout_action_publisher] Rollout request received.')
        actions = np.array(req.actions).reshape(-1, self.action_dim)
        success = self.run_rollout(actions)
        states = np.array(self.S)

        return {'states': states.reshape((-1,)), 'success' : success}

    def CallbackRolloutV2(self, req):
        print('[rollout_action_publisher] Rollout request received.')
        actions = np.array(req.actions).reshape(-1, self.action_dim)
        success = self.run_rollout_v2(actions)
        states = np.array(self.S)

        return {'states': states.reshape((-1,)), 'success' : success}

if __name__ == '__main__':
    try:
        rolloutPublisher()
    except rospy.ROSInterruptException:
        pass