"""

PyTOpts FEM module

Contains an initiation of a FEM simulation and two solvers, a linear and a nonlinear.

The initiation of the FEM simulation determine the number degrees of freedom,
number of elements, the freedofs and the position of each element. All this is 
independet of the type of solver. 

The linear solver starts by determine the stiffness matrix K according to the material model.
With this and the global external forces is the displacement calculated.

The nonlinear solver uses the Newton-Raphson iteration method. It calculates the
internal forcevector and checks the differens with the external force vector. 
The resultant will influence the next guess of the displacements.


Written 2021-05
Made By: Daniel Pettersson & Erik Säterskog
"""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


class FE():
    
    
    def __init__(self,edof,coords,mp,fixdofs):
        self.mp = mp
        self.E=mp['E']
        self.v=mp['nu']
        
        self.ndof=np.max(edof)
        self.nElem=np.size(edof,0)
        nx=coords[:,0]
        ny=coords[:,1]
        
        #Initialize Vecotors and Matrices
        self.K = coo_matrix((self.ndof,self.ndof))
        self.U = np.zeros([self.ndof,1])
        
        
        #Check element type
        if len(edof[0,:])==6:   #Triangular Element
            
            self.elemX=np.zeros([self.nElem,3])
            self.elemY=np.zeros([self.nElem,3])
        elif len(edof[0,:])==8: #Quad Element
            
            self.elemX=np.zeros([self.nElem,4])
            self.elemY=np.zeros([self.nElem,4])
        else:
            raise Exception('Unrecognized Element Shape, Check eDof Matrix')
    
        #Find The coordinates for each element's nodes
        for elem in range(self.nElem):
            
            nNode=np.ceil(np.multiply(edof[elem,:],0.5))-1
            nNode=nNode.astype(int)
            
            self.elemX[elem,:]=nx[nNode[0:8:2]]
            self.elemY[elem,:]=ny[nNode[0:8:2]]
        
        alldofs = range(self.ndof)        
        self.freedofs = np.setdiff1d(alldofs, fixdofs)
        self.edof = edof
        
    
        
    def fe(self,x,SIMP_penal,F,ep,elementFun,materialFun, eq=None):
        
        """
        INPUT:
            x          - element densities, design variables
            SIMP_penal - Penaltyfactor preventing x to be between 0-1
            eDof       - Element degrees of freedom
            coord      - Node coordinates both in x- and y-direction
            fixDofs    - Degrees of freedom prescribed by boundary condition
            F          - Forcevector
            ep[thickness, linear, el_type]
                 thickness  - thickness of the 2D material
                 linear     - True-linear, False-nonlinear
                 el_type    - 2 indicates triangular elements and 3 indicates
                 quad elements.
            mp[E,nu,eps_y]
                 E          - Young's modulus
                 nu         - Poission's ratio
                 eps_y      - Yielding strain for bilinear material model
                         
                         
        OUTPUT:
            U           -Displacement vector
            fext_tilde  -External force vector with only body forces
            fextGlobal  -External force vector
            K           -Stiffness matrix
        
          
        """
        
        #Settings
        epLin=ep.copy()
        epLin[3]=1

        row=[]
        col=[]
        data=[]
        fextGlobal = F.copy()
        fext_tilde = np.zeros(F.shape)
        
        for elem in range(self.nElem):  
                
            edofIndex=(self.edof[elem,:]-1).tolist() 
            edofIndex1D=np.ix_(self.edof[elem,:]-1)
            
            Ke, fint, fext, stress, epsilon=elementFun(np.zeros(np.size(self.edof,1),), self.elemX[elem,:], self.elemY[elem,:], epLin, self.mp, materialFun, eq) 

            Ke=np.matrix(Ke)               

            row.extend(edofIndex*len(edofIndex))
            col.extend(np.repeat(edofIndex,len(edofIndex)))
            data.extend(np.reshape(Ke*x[elem][0]**SIMP_penal,np.size(Ke)).tolist()[0])
            
            fextGlobal[edofIndex1D] += fext*x[elem][0]
            fext_tilde[edofIndex1D] += fext 

        K=coo_matrix((data,(row,col)),shape=(self.ndof,self.ndof))
        K=K.tocsc()


        self.U[np.ix_(self.freedofs)] = spsolve(K[np.ix_(self.freedofs,self.freedofs)],fextGlobal[np.ix_(self.freedofs)]).reshape(len(self.freedofs),1)

        
        return self.U, fext_tilde, fextGlobal, K
    
    
    def fe_nl(self,x,SIMP_const,F,ep,elementFun, materialFun, eq=None):
        """
        INPUT:
            x          - element densities, design variables
            SIMP_const - Penaltyfactor preventing x to be between 0-1
            eDof       - Element degrees of freedom
            coord      - Node coordinates both in x- and y-direction
            fixDofs    - Degrees of freedom prescribed by boundary condition
            F          - Forcevector
            ep[thickness, linear, el_type]
                 thickness  - thickness of the 2D material
                 linear     - True-linear, False-nonlinear
                 el_type    - 2 indicates triangular elements and 3 indicates
                 quad elements.
            mp[E,nu,eps_y]
                 E          - Young's modulus
                 nu         - Poission's ratio
                 eps_y      - Yielding strain for bilinear material model
            elementFun  -Element function
            materialFun -Material model
            eq          -Body force
                         
                         
        OUTPUT:
            U           -Displacement vector
            dR          -Derivative of Residual
            sig_VM      -Von Mises stress
            fext_tilde  -External force vector with only body forces
            fextGlobal  -External force vector
            eps_h       -Hydrostatic strain
            freedofs    -Free degrees of freedom
            K           -Stiffness matrix
        
          
        """
        #Settings
        err=1e9                  # Setting an error, arbritary big.
        TOL=1e-11    # Setting a resonable low tolerance. 
        
        U,fext_tilde, fextGlobal, K = FE.fe(self, x, SIMP_const, F, ep, elementFun, materialFun,eq)
        

        #lambdaF = U.copy()
        
        index1D=np.ix_(self.freedofs)
        index2D=np.ix_(self.freedofs,self.freedofs)
        
        newtonIt = 0
        sig_VM = np.zeros(np.shape(x))
        eps_h  = sig_VM.copy()
        if ep[3]==1:  #Check if linear.
            return U, [], [], fext_tilde, fextGlobal, eps_h, self.freedofs, K

        
        #Newton iteration loop until convergens.
        while err>TOL:
            row=[]
            col=[]
            data=[]
            newtonIt +=1
            R = np.zeros(np.shape(F)) 
            dR = np.zeros([self.nElem,np.size(self.edof,1)])
            fext_tilde = np.zeros(U.shape)
            fextGlobal = F.copy()
            fintGlobal = np.zeros(U.shape)
            
            for elem in range(self.nElem):
                
                edofIndexList=(self.edof[elem,:]-1).tolist()
                edofIndex1D=np.ix_(self.edof[elem,:]-1)
                
                Ue = U[edofIndex1D]
                
                Ke, fint, fext, sig, epsilon=elementFun(Ue.reshape(np.size(self.edof,1),), self.elemX[elem,:], self.elemY[elem,:], ep, self.mp, materialFun, eq) 
                Ke=np.matrix(Ke)
                
                fextGlobal[edofIndex1D]+=fext*x[elem][0]
                fintGlobal[edofIndex1D]+=fint*x[elem][0]**SIMP_const
                fext_tilde[edofIndex1D]+=fext 
                dR[elem,:] = (SIMP_const*x[elem][0]**(SIMP_const-1)*fint).reshape(np.size(self.edof,1),)-(fext).reshape(np.size(self.edof,1),)
                
                row.extend(edofIndexList*len(edofIndexList))
                col.extend(np.repeat(edofIndexList,len(edofIndexList)))
                data.extend(np.reshape(Ke*x[elem][0]**SIMP_const,np.size(Ke)).tolist()[0])
                
                sig_VM[elem]= np.sqrt(((sig[0]-sig[1])**2+(sig[1]-sig[2])**2+(sig[2]-sig[0])**2)/2+3*(sig[3]**2+sig[4]**2+sig[5]**2))
                eps_h[elem] = sum(epsilon[:2])/3
    
            
            K=coo_matrix((data,(row,col)),shape=(self.ndof,self.ndof))
            K=K.tocsc()
              
            R=fintGlobal-fextGlobal
            err = np.linalg.norm(R[self.freedofs])
            
            if newtonIt ==100:
                break
            
            TOL=1e-11*max(max(abs(fextGlobal)),1e4)
            
            U[index1D] = U[index1D] - spsolve(K[index2D],R[self.freedofs]).reshape(len(self.freedofs),1)
                    
      
     
        
        print('N.iters:    ' + str(newtonIt))
        print('Final error:' + str(err))
        return U, dR, sig_VM, fext_tilde, fextGlobal, eps_h, self.freedofs, K

    
   








