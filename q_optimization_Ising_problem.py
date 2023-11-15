# Script to optimise the Hamiltonian, starting directly from the Ising Hamiltonian
# or build the Pauli representation from the problem may be more efficient rather than converting it
# too complex though for now 
import numpy as np
import pandas as pd
import csv
import matplotlib.pyplot as plt
from copy import deepcopy

## configure the hamiltonian from the values calculated classically with pyrosetta
df1 = pd.read_csv("one_body_terms.csv")
q = df1['E_ii'].values
num = len(q)

print('Qii values: \n', q)

df = pd.read_csv("two_body_terms.csv")
value = df['E_ij'].values
Q = np.zeros((num,num))
n = 0

for i in range(0, num-2):
    if i%2 == 0:
        Q[i][i+2] = deepcopy(value[n])
        Q[i+2][i] = deepcopy(value[n])
        Q[i][i+3] = deepcopy(value[n+1])
        Q[i+3][i] = deepcopy(value[n+1])
        n += 2
    elif i%2 != 0:
        Q[i][i+1] = deepcopy(value[n])
        Q[i+1][i] = deepcopy(value[n])
        Q[i][i+2] = deepcopy(value[n+1])
        Q[i+2][i] = deepcopy(value[n+1])
        n += 2

print('\nQij values: \n', Q)

H = np.zeros((num,num))

for i in range(num):
    for j in range(i+1, num):
        H[i][j] = np.multiply(0.25, Q[i][j])

for i in range(num):
    H[i][i] = -0.5 * q[i] - sum(0.5 * Q[i][j] for j in range(num) if i != j)

print('\nH: \n', H)

# add penalty terms to the matrix so as to discourage the selection of two rotamers on the same residue - implementation of the Hammings constraint
def add_penalty_term(M, penalty_constant, residue_pairs):
    for i, j in residue_pairs:
        M[i][j] += penalty_constant
        
    return M

P = 3
pairs = [(0,1), (2,3)]       #, (4,5), (6,7)]     #, (8,9), (10,11), (12,13)]

M = deepcopy(H)
M = add_penalty_term(M, P, pairs)       #matrix for qaoa

## Classical optimisation:
from scipy.sparse.linalg import eigsh
num_qubits = num

Z_matrix = np.array([[1, 0], [0, -1]])
identity = np.eye(2)

def construct_operator(qubit_indices, num_qubits):
    operator = np.eye(1)
    for qubit in range(num_qubits):
        if qubit in qubit_indices:
            operator = np.kron(operator, Z_matrix)
        else:
            operator = np.kron(operator, identity)
    return operator

C = np.zeros((2**num_qubits, 2**num_qubits))

for i in range(num_qubits):
    operator = construct_operator([i], num_qubits)
    C += H[i][i] * operator

for i in range(num_qubits):
    for j in range(i+1, num_qubits):
        operator = construct_operator([i, j], num_qubits)
        C += H[i][j] * operator

print('C :\n', C)

def create_hamiltonian(pairs, P, num_qubits):
    H_pen = np.zeros((2**num_qubits, 2**num_qubits))
    def tensor_term(term_indices):
        term = [Z_matrix if i in term_indices else identity for i in range(num_qubits)]
        result = term[0]
        for t in term[1:]:
            result = np.kron(result, t)
        return result
    
    for pair in pairs:
        term = tensor_term(pair)
        H_pen += P * term

    return H_pen

# ZZII = np.kron(np.kron(np.kron(Z_matrix, Z_matrix), identity), identity)
# IIZZ = np.kron(np.kron(np.kron(identity, identity), Z_matrix), Z_matrix)
# H_penalty = P * (ZZII + IIZZ)

H_penalty = create_hamiltonian(pairs, P, num_qubits)

H_tot = C + H_penalty

# Extract the ground state energy and wavefunction
# using sparse representation so as to be able to generalise to larger systems
eigenvalues, eigenvectors = eigsh(H_tot, k=num, which='SA')
print("\n\nClassical optimisation results. \n")
print("Ground energy eigsh: ", eigenvalues[0])
print("ground state wavefuncion eigsh: ", eigenvectors[:,0])


## Quantum optimisation
#  Find minimum value using optimisation technique of QAOA
from qiskit import Aer, QuantumCircuit
from qiskit_algorithms.minimum_eigensolvers import QAOA
from qiskit.quantum_info.operators import Operator, Pauli, SparsePauliOp
from qiskit_algorithms.optimizers import COBYLA
from qiskit.primitives import Sampler

def X_op(i, num_qubits):
    """Return an X Pauli operator on the specified qubit in a num-qubit system."""
    op_list = ['I'] * num_qubits
    op_list[i] = 'X'
    return SparsePauliOp(Pauli(''.join(op_list)))


def generate_pauli_zij(n, i, j):
    if i<0 or i >= n or j<0 or j>=n:
        raise ValueError(f"Indices out of bounds for n={n} qubits. ")
   
    pauli_str = ['I']*n

    if i == j:
        pauli_str[i] = 'Z'
    else:
        pauli_str[i] = 'Z'
        pauli_str[j] = 'Z'

    return Pauli(''.join(pauli_str))


q_hamiltonian = SparsePauliOp(Pauli('I'*num_qubits), coeffs=[0])

for i in range(num_qubits):
    for j in range(i+1, num_qubits):
        if M[i][j] != 0:
            pauli = generate_pauli_zij(num_qubits, i, j)
            op = SparsePauliOp(pauli, coeffs=[M[i][j]])
            q_hamiltonian += op

for i in range(num_qubits):
    pauli = generate_pauli_zij(num_qubits, i, i)
    Z_i = SparsePauliOp(pauli, coeffs=[M[i][i]])
    q_hamiltonian += Z_i

def format_sparsepauliop(op):
    terms = []
    labels = [pauli.to_label() for pauli in op.paulis]
    coeffs = op.coeffs
    for label, coeff in zip(labels, coeffs):
        terms.append(f"{coeff:.10f} * {label}")
    return '\n'.join(terms)

print(f"\nThe hamiltonian constructed using Pauli operators is: \n", format_sparsepauliop(q_hamiltonian))


#the mixer in QAOA should be a quantum operator representing transitions between configurations
mixer_op = sum(X_op(i,num_qubits) for i in range(num_qubits))

p = 10  # Number of QAOA layers
initial_point = np.ones(2 * p)
qaoa = QAOA(sampler=Sampler(), optimizer=COBYLA(), reps=p, mixer=mixer_op, initial_point=initial_point)
result = qaoa.compute_minimum_eigenvalue(q_hamiltonian)
print("\n\nThe result of the quantum optimisation using QAOA is: \n")
print('best measurement', result.best_measurement)
print(result)

k = 0

for i in range(num_qubits):
    k += 0.5 * q[i]

for i in range(num_qubits):
    for j in range(num_qubits):
        if i != j:
            k += 0.5 * 0.25 * Q[i][j]

print('eigenvalue: ', np.real(result.best_measurement['value']) + 2*P + k)

# alternative ground state energy calculation with Ising model
bitstring = result.best_measurement['bitstring']
spins = [1 if bit == '0' else -1 for bit in bitstring]

energy = 0

for i in range(num_qubits):
    for j in range(i+1, num_qubits):
        energy += H[i][j] * spins[i] * spins[j]

for i in range(num_qubits):
    energy +=  H[i][i] * spins[i]

print(f"The energy for bitstring {bitstring} with J is: {energy + k}")

# with QUBO model
bits = [0 if bit == '0' else 1 for bit in bitstring]

en = 0

for i in range(num_qubits):
    en += q[i] * bits[i]

for i in range(num_qubits):
    for j in range(num_qubits):
        if Q[i][j] != 0:
            if i != j:
                en += 0.5 * Q[i][j] * bits[i] * bits[j]

print(f"The energy for bitstring {bitstring} with Q is: {en}")

print('g.s energy: ', eigenvalues[0]+2*P+k)