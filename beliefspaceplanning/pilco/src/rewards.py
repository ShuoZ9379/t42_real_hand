import abc
import tensorflow as tf
from gpflow import Parameterized, Param, params_as_tensors, settings
import numpy as np

float_type = settings.dtypes.float_type


class Reward(Parameterized):
    def __init__(self):
        Parameterized.__init__(self)

    @abc.abstractmethod
    def compute_reward(self, m, s):
        raise NotImplementedError


class ExponentialReward(Reward):
    def __init__(self, state_dim, W=None, t=None):
        Reward.__init__(self)
        self.state_dim = state_dim
        if W is not None:
            self.W = Param(np.reshape(W, (state_dim, state_dim)), trainable=False)
        else:
            self.W = Param(np.ones((state_dim, state_dim)), trainable=False)
        if t is not None:
            self.t = Param(np.reshape(t, (1, state_dim)), trainable=False)
        else:
            self.t = Param(np.zeros((1, state_dim)), trainable=False)

    @params_as_tensors
    def compute_reward(self, m, s):
        '''
        Reward function, calculating mean and variance of rewards, given
        mean and variance of state distribution, along with the target State
        and a weight matrix.
        Input m : [1, k]
        Input s : [k, k]

        Output M : [1, 1]
        Output S  : [1, 1]
        '''
        # TODO: Clean up this

        SW = s @ self.W

        iSpW = tf.transpose(
                tf.matrix_solve( (tf.eye(self.state_dim, dtype=float_type) + SW),
                tf.transpose(self.W), adjoint=True))

        muR = tf.exp(-(m-self.t) @  iSpW @ tf.transpose(m-self.t)/2) / \
                tf.sqrt( tf.linalg.det(tf.eye(self.state_dim, dtype=float_type) + SW) )

        i2SpW = tf.transpose(
                tf.matrix_solve( (tf.eye(self.state_dim, dtype=float_type) + 2*SW),
                tf.transpose(self.W), adjoint=True))

        r2 =  tf.exp(-(m-self.t) @ i2SpW @ tf.transpose(m-self.t)) / \
                tf.sqrt( tf.linalg.det(tf.eye(self.state_dim, dtype=float_type) + 2*SW) )

        sR = r2 - muR @ muR
        muR.set_shape([1, 1])
        sR.set_shape([1, 1])
        return muR, sR

class ExponentialRewardAxis(Reward):
    def __init__(self, state_dim, W=None, t=None):
        Reward.__init__(self)
        self.state_dim = state_dim-1
        state_dim = self.state_dim
        t = t[:self.state_dim]

        if W is not None:
            self.W = Param(np.reshape(W, (state_dim, state_dim)), trainable=False)
        else:
            self.W = Param(np.ones((state_dim, state_dim)), trainable=False)
        if t is not None:
            self.t = Param(np.reshape(t, (1, state_dim)), trainable=False)
        else:
            self.t = Param(np.zeros((1, state_dim)), trainable=False)

    @params_as_tensors
    def compute_reward(self, m, s):
        '''
        Reward function, calculating mean and variance of rewards, given
        mean and variance of state distribution, along with the target State
        and a weight matrix.
        Input m : [1, k]
        Input s : [k, k]

        Output M : [1, 1]
        Output S  : [1, 1]
        '''
        # TODO: Clean up this

        m = m[:,:self.state_dim:]
        s = s[:self.state_dim,:self.state_dim]

        SW = s @ self.W

        iSpW = tf.transpose(
                tf.matrix_solve( (tf.eye(self.state_dim, dtype=float_type) + SW),
                tf.transpose(self.W), adjoint=True))

        muR = tf.exp(-(m-self.t) @  iSpW @ tf.transpose(m-self.t)/2) / \
                tf.sqrt( tf.linalg.det(tf.eye(self.state_dim, dtype=float_type) + SW) )

        i2SpW = tf.transpose(
                tf.matrix_solve( (tf.eye(self.state_dim, dtype=float_type) + 2*SW),
                tf.transpose(self.W), adjoint=True))

        r2 =  tf.exp(-(m-self.t) @ i2SpW @ tf.transpose(m-self.t)) / \
                tf.sqrt( tf.linalg.det(tf.eye(self.state_dim, dtype=float_type) + 2*SW) )

        sR = r2 - muR @ muR
        muR.set_shape([1, 1])
        sR.set_shape([1, 1])
        return muR, sR

class ExponentialRewardCustom(Reward):
    def __init__(self, state_dim, W=None, t=None):
        Reward.__init__(self)
        self.state_dim = state_dim

        if W is not None:
            self.W = Param(np.reshape(W, (state_dim, state_dim)), trainable=False)
        else:
            self.W = Param(np.ones((state_dim, state_dim)), trainable=False)
        if t is not None:
            self.t = Param(np.reshape(t, (1, state_dim)), trainable=False)
        else:
            self.t = Param(np.zeros((1, state_dim)), trainable=False)

    @params_as_tensors
    def compute_reward(self, m, s):
        '''
        Reward function, calculating mean and variance of rewards, given
        mean and variance of state distribution, along with the target State
        and a weight matrix.
        Input m : [1, k]
        Input s : [k, k]

        Output M : [1, 1]
        Output S  : [1, 1]
        '''
        # TODO: Clean up this

        SW = s @ self.W

        muR = tf.exp(-(m-self.t) @ tf.transpose(m-self.t)/2)

        sR = muR*0.
        muR.set_shape([1, 1])
        sR.set_shape([1, 1])
        return muR, sR