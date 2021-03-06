"""
Elastic material model.
Inputs:
    eps     -epsilon, the strain
    mp[E,nu,eps_y]
             E          - Young's modulus
             nu         - Poission's ratio
             eps_y      - Yielding strain for bilinear material model

Outputs:
    sigma   -Stress
    D       -Constitutive matrix


Written 2021-05
Made By: Daniel Pettersson & Erik Säterskog
"""

import numpy as np

def elastic(eps,mp):
    E = mp['E']
    nu = mp['nu']
    G = E/(2*(1+nu))
    K = E/(3*(1-2*nu))
    
    I_v = np.array([1,1,1,0,0,0])
    I_vT = np.array([[1],[1],[1],[0],[0],[0]])
    I_s = np.diag([1,1,1,0.5,0.5,0.5])
    I_sdev = (I_s - 1/3*I_v*I_vT)
    
    sigma = np.zeros([6,])
    D = np.zeros([6,6])
    
    
    D  =K*I_v*I_vT+ 2*G*I_sdev
    sigma = np.matmul(D,eps)
    sigma.shape = (6,1)
    return sigma, D
