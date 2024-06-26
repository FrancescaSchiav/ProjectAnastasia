import numpy as np
import pandas as pd
import itertools
import functools
import operator
from itertools import combinations
from qiskit.visualization import plot_histogram
import matplotlib.pyplot as plt

qubit_per_res = 2
num_rot = 2**qubit_per_res

df1 = pd.read_csv("energy_files/one_body_terms.csv")
q = df1['E_ii'].values
num = len(q)
N_res = int(num/num_rot)

df = pd.read_csv("energy_files/two_body_terms.csv")
v = df['E_ij'].values
numm = len(v)

print("q: \n", q)

num_qubits = N_res * qubit_per_res

## Quantum optimisation
from qiskit_aer import Aer
from qiskit_algorithms.minimum_eigensolvers import QAOA
from qiskit.quantum_info import Pauli, SparsePauliOp
from qiskit_algorithms.optimizers import COBYLA
from qiskit.primitives import Sampler

## Mapping to qubits
H_self = SparsePauliOp(Pauli('I'* num_qubits), coeffs=[0])
H_int = SparsePauliOp(Pauli('I'* num_qubits), coeffs=[0]) 

def N_0(i, n):
    pauli_str = ['I'] * n
    pauli_str[i] = 'Z'
    z_op = SparsePauliOp(Pauli(''.join(pauli_str)), coeffs=[0.5])
    i_op = SparsePauliOp(Pauli('I'*n), coeffs=[0.5])
    return z_op + i_op

def N_1(i, n):
    pauli_str = ['I'] * n
    pauli_str[i] = 'Z'
    z_op = SparsePauliOp(Pauli(''.join(pauli_str)), coeffs=[-0.5])
    i_op = SparsePauliOp(Pauli('I'*n), coeffs=[0.5])
    return z_op + i_op


def create_pauli_operators(num_qubits, qubits_per_res):
    operators = []
    for i in range(0, num_qubits, qubits_per_res):
        # Generate all combinations of N_0 and N_1 for the residue
        for comb in itertools.product([N_0, N_1], repeat=qubits_per_res):
            ops = [func(j, num_qubits) for j, func in enumerate(comb, start=i)]
            # Now you have a list of operators for each qubit in the residue
            full_op = functools.reduce(operator.matmul, ops)
            operators.append(full_op)
    return operators

for i, op in enumerate(create_pauli_operators(num_qubits, qubit_per_res)):
    H_self += q[i] * op
    if i >= len(q) - 1:
        break

def create_interaction_operators(num_qubits, qubits_per_res, v):
    H_int = SparsePauliOp(Pauli('I' * num_qubits), coeffs=[0])
    v_index = 0
    
    # Iterate over all unique pairs of residues
    for res1, res2 in combinations(range(0, num_qubits, qubits_per_res), 2):
        # Generate all combinations of N_0 and N_1 for each qubit in the residue
        for comb1 in itertools.product([N_0, N_1], repeat=qubits_per_res):
            for comb2 in itertools.product([N_0, N_1], repeat=qubits_per_res):
                op_list1 = [func(i + res1, num_qubits) for i, func in enumerate(comb1)]
                op_list2 = [func(j + res2, num_qubits) for j, func in enumerate(comb2)]
                
                # Now you have two lists of operators, one for each residue in the pair
                full_op1 = functools.reduce(operator.matmul, op_list1)
                full_op2 = functools.reduce(operator.matmul, op_list2)
                
                H_int += v[v_index] * full_op1 @ full_op2
                v_index += 1
                
                if v_index >= len(v) - 1:
                    break
            if v_index >= len(v) - 1:
                break
        if v_index >= len(v) - 1:
            break

    return H_int

H_int = create_interaction_operators(num_qubits, qubit_per_res, v)

H_gen = H_self + H_int

# # Convert H_gen to a list of tuples (coefficient, Pauli string)
# pauli_terms = []
# for pauli, coeff in zip(H_gen.paulis, H_gen.coeffs):
#     pauli_str = pauli.to_label()
#     pauli_terms.append((coeff, pauli_str))

# # Print out the formatted Hamiltonian
# for coeff, pauli_str in pauli_terms:
#     print(f"{coeff} * {pauli_str}")


def X_op(i, num):
    op_list = ['I'] * num
    op_list[i] = 'X'
    return SparsePauliOp(Pauli(''.join(op_list)))

mixer_op = sum(X_op(i,num_qubits) for i in range(num_qubits))
p = 1
initial_point = np.ones(2*p)
qaoa = QAOA(sampler=Sampler(), optimizer=COBYLA(), reps=p, mixer=mixer_op, initial_point=initial_point)
result_gen = qaoa.compute_minimum_eigenvalue(H_gen)
print("\n\nThe result of the quantum optimisation using QAOA is: \n")
print('best measurement', result_gen.best_measurement)
print('The ground state energy with QAOA is: ', np.real(result_gen.best_measurement['value']))


from qiskit_aer.noise import NoiseModel
from qiskit_ibm_provider import IBMProvider
from qiskit_aer import AerSimulator
from qiskit.circuit.library import QAOAAnsatz
from qiskit_ibm_runtime import QiskitRuntimeService, Options, Session, Sampler
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit.primitives import StatevectorEstimator
from qiskit_ibm_runtime import EstimatorV2 as Estimator
from qiskit_ibm_runtime import SamplerV2 as Sampler
from scipy.optimize import minimize

IBMProvider.save_account('25a4f69c2395dfbc9990a6261b523fe99e820aa498647f92552992afb1bd6b0bbfcada97ec31a81a221c16be85104beb653845e23eeac2fe4c0cb435ec7fc6b4', overwrite=True)
provider = IBMProvider()
available_backends = provider.backends()
print([backend.name for backend in available_backends])
service = QiskitRuntimeService(channel="ibm_quantum")
backend = service.backend("ibmq_qasm_simulator")
noise_model = NoiseModel.from_backend(backend)
simulator = AerSimulator(noise_model = noise_model)
print('Noise model', noise_model)

ansatz = QAOAAnsatz(H_gen, reps=2)
ansatz.decompose(reps=3).draw(output='mpl', style='iqp')

target = backend.target
pm = generate_preset_pass_manager(target=target, optimization_level=3)

ansatz_isa =pm.run(ansatz)
ansatz_isa.draw(output="mpl", idle_wires=False, style="iqp")

hamiltonian_isa = H_gen.apply_layout(ansatz_isa.layout)

def cost_func(params, ansatz, hamiltonian, estimator):
    pub = (ansatz, [hamiltonian], [params])
    result = estimator.run(pubs=[pub]).result()
    cost = result[0].data.evs[0]
    return cost

# # To run on cloud simulator
session = Session(backend=backend)
estimator = Estimator(session=session)
estimator.options.default_shots = 10_000
estimator.options.dynamical_decoupling.enable = True

sampler = Sampler(session=session)
sampler.options.default_shots = 10_000
sampler.options.dynamical_decoupling.enable = True

num_parameters = ansatz_isa.num_parameters
print(f"Number of parameters in the modified ansatz: {num_parameters}")
initial_point_isa = np.ones(2)
x0 = 2 * np.pi * np.random.rand(ansatz_isa.num_parameters)

qaoa1 = QAOA(sampler=sampler, optimizer=COBYLA(), reps=p, mixer=mixer_op, initial_point=x0)
result1 = qaoa1.compute_minimum_eigenvalue(hamiltonian_isa)
print('Running noisy simulation..')


# # To run on local simulator
# estimator = StatevectorEstimator()

# x0 = 2 * np.pi * np.random.rand(ansatz_isa.num_parameters)
# res = minimize(cost_func, x0, args=(ansatz_isa, hamiltonian_isa, estimator), method="COBYLA")
# print('res: ', res)

## as before
# options = Options()
# options.simulator = {
#     "noise_model":  noise_model,
#     "basis_gates": backend.configuration().basis_gates,
#     "seed_simulator": 42
# }
# options.execution.shots = 1000
# options.optimization_level = 0
# options.resilience_level = 0

# with Session(service=service, backend=backend) as session:
#     # sampler = Sampler(options=options)
#     sampler = Sampler(session=session)
#     qaoa1 = QAOA(sampler=sampler, optimizer=COBYLA(), reps=p, mixer=mixer_op, initial_point=initial_point_isa)
#     result1 = qaoa1.compute_minimum_eigenvalue(hamiltonian_isa)
#     print('Running noisy simulation..')

print("\n\nThe result of the noisy quantum optimisation using QAOA is: \n")
print('best measurement', result1.best_measurement)
print('Optimal parameters: ', result1.optimal_parameters)
print('The ground state energy with noisy QAOA is: ', np.real(result1.best_measurement['value']))


