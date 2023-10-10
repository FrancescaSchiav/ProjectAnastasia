import pyrosetta; pyrosetta.init()
from pyrosetta.teaching import *
from pyrosetta import *

from pyrosetta.rosetta.core.pack.rotamer_set import RotamerSets, RotamerSet
from pyrosetta.rosetta.core.pack.task import TaskFactory
from pyrosetta.rosetta.core.pack.rotamer_set import *
from pyrosetta.rosetta.core.pack.interaction_graph import InteractionGraphFactory
from pyrosetta.rosetta.core.pack.task import *

import csv
import sys
import numpy as np


#Using the protein Ras (PDB 6Q21)
pose = pyrosetta.pose_from_pdb("6Q21_A.pdb")
residue_count = pose.total_residue() # N residues

#Function to check for hydrogen atoms in a Pose
def has_hydrogen_atoms(pose):
    for i in range(1, pose.total_residue() + 1):
        for j in range(1, pose.residue(i).natoms() + 1):
            if pose.residue(i).atom_name(j)[0] == 'H':
                return True
    return False

#Check if the pose has hydrogen atoms
if has_hydrogen_atoms(pose):
    print("Hydrogen atoms are present in the pose.")
else:
    print("No hydrogen atoms found in the pose.")

#Define a score function with the default weights ref2015
sfxn = get_score_function(True)

#Relax the structure to refine it 
relax_protocol = pyrosetta.rosetta.protocols.relax.FastRelax()
relax_protocol.set_scorefxn(sfxn)
# relax_protocol.constrain_relax_to_start_coords(True)
# relax_protocol.set_add_hydrogens(True)
relax_protocol.apply(pose)

if has_hydrogen_atoms(pose):
    print("Now hydrogen atoms are present in the pose.")
else:
    print("still no hydrogens!!")

sfxn.show(pose)

#Print the energy values of each residue
for i in range(1, residue_count + 1): 
    print(pose.energies().show(i))



#For each resdiue now I want to calculate each rotamer
task_pack = TaskFactory.create_packer_task(pose) # is a class in PyRosetta that provides methods for creating and manipulating various types of tasks that control how certain operations are performed on a protein structure (pose).
            # A packer task is a task that defines which residues in a protein structure (pose) are allowed to move or be optimized during a packing step of a computational protein design or refinement protocol.
rotsets = RotamerSets()

#Set up and calculate pairwise interaction energies between rotamers of two specific residues (1 and 2) 
pose.update_residue_neighbors() # updates the neighbour information for residues in the proetein structure
sfxn.setup_for_packing(pose, task_pack.designing_residues(), task_pack.designing_residues()) # prepares the scoring function for packing by specifying which residues are allowed to be designed (optimized) based on the task pack, designing_residues() returns the list of residues that are designated as designable in the task pack.
# packer_task = pyrosetta.rosetta.core.pack.task.PackerTask(pose.total_residue())
# packer_graph = pyrosetta.rosetta.core.pack.creat_packer_graph(pose, packer_task)
packer_neighbor_graph = pyrosetta.rosetta.core.pack.create_packer_graph(pose, sfxn, task_pack) #The neighbor graph represents the spatial relationships between residues and is essential for efficient energy calculations.
rotsets.set_task(task_pack) #associates the rotamer sets with the task pack, indicating which residues and rotamers will be considered during the analysis.
rotsets.build_rotamers(pose, sfxn, packer_neighbor_graph) #builds rotamers for the protein's residues. Rotamers are alternative conformations of side chains that are sampled during protein modeling.
rotsets.prepare_sets_for_packing(pose, sfxn) #prepares the rotamer sets for packing calculations by potentially reducing the set of rotamers based on their energies.
ig = InteractionGraphFactory.create_interaction_graph(task_pack, rotsets, pose, sfxn, packer_neighbor_graph)
print("built", rotsets.nrotamers(), "rotamers at", rotsets.nmoltenres(), "positions.")
rotsets.compute_energies(pose, sfxn, packer_neighbor_graph, ig, 1) #This computes energies associated with the rotamers in the context of the protein structure. 


#Loop that calculates the pairwise interaction energies between different rotamers (s_i and s_j) at positions 1 and 2 in the protein. The energies are stored in the E 

#Analyse energy between residues
#to isolate the contribution from particular pairs of residues

max_rotamers = 0
for residue_number in range(1, residue_count):
    n_rots = rotsets.nrotamers_for_moltenres(residue_number)
    if n_rots > max_rotamers:
        max_rotamers = n_rots

E = np.zeros((max_rotamers, max_rotamers))
output_file = "score_summary.csv"


with open(output_file, "w") as f:
    for residue_i in range(1, residue_count):
        rotamer_set_i = RotamerSet(pose, residue_i)

        for rotamer_i in range(rotamer_set_i.num_rotamers()):
            rotamer_set_i.set_rotamer(rotamer_i)

            for residue_j in range(1, residue_count):
                if residue_i != residue_j:
                    rotamer_set_j = RotamerSet(residue_j)

                    for rotamer_j in range(rotamer_set_j.num_rotamers()):
                        rotamer_set_j.set_rotamer(rotamer_j)

                        interaction_energy = pose.energies().onebody_energies(residue_i) + pose.energies().onebody_energies(residue_j)
                        interaction_energy += pose.energies().two_body_energy(residue_i, residue_j)

                        E[rotamer_i, rotamer_j] = interaction_energy
                    
        print("Interaction energy between rotamers of residue 1 and 2:", E[rotamer_i, rotamer_j])
        f.write(f"Score Interactions between rotamer {rotamer_i} and rotamer {rotamer_j} --->> {E[rotamer_i,rotamer_j]}")





