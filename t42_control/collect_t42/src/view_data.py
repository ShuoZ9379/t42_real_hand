#!/usr/bin/env python

import numpy as np
import time
import random
import pickle
import os.path
import matplotlib.pyplot as plt
from transition_experience import *


def main():

    texp = transition_experience(Load = True, discrete=True, postfix='', with_fingers = False) #, Object = 'cyl35_red'

    texp.process_transition_data(stepSize = 1, plot = True)
    # texp.process_svm(stepSize = 1)

    # texp.plot_data()

    return 1


if __name__=='__main__':
    main()