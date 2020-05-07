#!/usr/bin/env python
# Import all the functions from opensbli
from opensbli import *
import copy
from opensbli.utilities.helperfunctions import substitute_simulation_parameters
from sympy import pi, sin, cos
from SFD import *

# Problem dimension
ndim = 2
# Define the compresible Navier-Stokes equations in Einstein notation, by default the scheme is Central no need to
mass = "Eq(Der(rho,t), - Skew(rho*u_j,x_j))"
momentum = "Eq(Der(rhou_i,t) , - Skew(rhou_i*u_j, x_j) - Der(p,x_i)  + Der(tau_i_j,x_j))"
energy = "Eq(Der(rhoE,t), - Skew(rhoE*u_j,x_j) - Conservative(p*u_j,x_j) + Der(q_j,x_j) + Der(u_i*tau_i_j ,x_j))"

# Substitutions used in the equations
stress_tensor = "Eq(tau_i_j, (1.0/Re)*(Der(u_i,x_j)+ Der(u_j,x_i)- (2/3)* KD(_i,_j)* Der(u_k,x_k)))"
heat_flux = "Eq(q_j, (1.0/((gama-1)*Minf*Minf*Pr*Re))*Der(T,x_j))"

substitutions = [stress_tensor, heat_flux]
# Constants that are used
constants = ["Re", "Pr", "gama", "Minf", "mu"]

# symbol for the coordinate system in the equations
coordinate_symbol = "x"

# Constituent relations used in the system
velocity = "Eq(u_i, rhou_i/rho)"
pressure = "Eq(p, (gama-1)*(rhoE - rho*(1/2)*(KD(_i,_j)*u_i*u_j)))"
temperature = "Eq(T, p*gama*Minf*Minf/(rho))"

# Instantiate EinsteinEquation class for expanding the Einstein indices in the equations
einstein_eq = EinsteinEquation()

# Expand the simulation equations, for this create a simulation equations class
simulation_eq = SimulationEquations()

# Expand mass and add the expanded equations to the simulation equations
eqns = einstein_eq.expand(mass, ndim, coordinate_symbol, substitutions, constants)
simulation_eq.add_equations(eqns)
# Expand momentum add the expanded equations to the simulation equations
eqns = einstein_eq.expand(momentum, ndim, coordinate_symbol, substitutions, constants)
simulation_eq.add_equations(eqns)
# Expand energy equation add the expanded equations to the simulation equations
eqns = einstein_eq.expand(energy, ndim, coordinate_symbol, substitutions, constants)
simulation_eq.add_equations(eqns)

# Expand the constituent relations and them to the constituent relations class
constituent = ConstituentRelations()  # Instantiate constituent relations object
# Expand momentum add the expanded equations to the constituent relations
eqns = einstein_eq.expand(velocity, ndim, coordinate_symbol, substitutions, constants)
constituent.add_equations(eqns)
# Expand pressure add the expanded equations to the constituent relations
eqns = einstein_eq.expand(pressure, ndim, coordinate_symbol, substitutions, constants)
constituent.add_equations(eqns)
# Expand temperature add the expanded equations to the constituent relations
eqns = einstein_eq.expand(temperature, ndim, coordinate_symbol, substitutions, constants)
constituent.add_equations(eqns)

metriceq = MetricsEquation()
metriceq.generate_transformations(ndim, coordinate_symbol, [(True, True), (True, True)], 2)
simulation_eq.apply_metrics(metriceq)

# Create a simulation block
block = SimulationBlock(ndim, block_number=0)

# Local dictionary for parsing the expressions
local_dict = {"block": block, "GridVariable": GridVariable, "DataObject": DataObject}

# Initial conditions as strings
u0 = "Eq(GridVariable(u0),1.0)"
u1 = "Eq(GridVariable(u1), 0.0,)"
p = "Eq(GridVariable(p), 1/(gama*Minf*Minf))"
r = "Eq(GridVariable(r), gama*Minf*Minf*p)"

rho = "Eq(DataObject(rho), r)"
rhou0 = "Eq(DataObject(rhou0), r*u0)"
rhou1 = "Eq(DataObject(rhou1), r*u1)"
rhoE = "Eq(DataObject(rhoE), p/(gama-1) + 0.5* r *(u0**2+ u1**2))"

eqns = [u0, u1, p, r, rho, rhou0, rhou1, rhoE]

# parse the initial conditions
initial_equations = [parse_expr(eq, local_dict=local_dict) for eq in eqns]
initial = GridBasedInitialisation()
initial.add_equations(initial_equations)

# Create a schemes dictionary to be used for discretisation
schemes = {}
# Central scheme for spatial discretisation and add to the schemes dictionary
cent = Central(4)
schemes[cent.name] = cent
# RungeKutta scheme for temporal discretisation and add to the schemes dictionary
rk = RungeKuttaLS(3, formulation='SSP')
schemes[rk.name] = rk

# Create boundaries, one for each side per dimension
q_vector = flatten(simulation_eq.time_advance_arrays)
boundaries = []
direction = 0
# Force the shared coordinate line to be one-sided
dummy_eqn = [OpenSBLIEq(DataObject('test'), 0.0)]
boundaries += [DirichletBC(direction, 0, dummy_eqn)]
boundaries += [DirichletBC(direction, 1, dummy_eqn)]
# Apply a periodic boundary over the shared mesh line
# boundaries += [PeriodicBC(direction, 0)]
# boundaries += [PeriodicBC(direction, 1)]
# Isothermal wall in x1 direction
gama, Minf = symbols('gama Minf', **{'cls': ConstantObject})
# Energy on the wall is set
wall_energy = [Eq(q_vector[3], q_vector[0] / (gama * Minf**2.0 * (gama - S.One)))]
direction = 1
lower_wall_eq = wall_energy[:]
boundaries += [IsothermalWallBC(direction, 0, lower_wall_eq)]
# Far field boundary
direction, side = 1,1
boundaries += [DirichletBC(direction, side, initial_equations)]
# set the boundaries for the block
block.set_block_boundaries(boundaries)

# Set the IO class to write out arrays
kwargs = {'iotype': "Write"}
h5 = iohdf5(save_every=10000, **kwargs)
h5.add_arrays(simulation_eq.time_advance_arrays)
h5.add_arrays([DataObject('x0'), DataObject('x1'),  DataObject('D00'), DataObject('D01'), DataObject('D10'), DataObject('D11')])
kwargs = {'iotype': "Read"}
h5_read = iohdf5(**kwargs)
h5_read.add_arrays([DataObject('x0'), DataObject('x1')])
block.setio([h5, h5_read])

# Add SFD filtering
SFD = SFD(block, chifilt=0.1, omegafilt=1.0/0.75)
# Set the equations to be solved on the block
block.set_equations([constituent, simulation_eq, initial, metriceq] + SFD.equation_classes)
# set the discretisation schemes
block.set_discretisation_schemes(schemes)

# Discretise the equations on the block
block.discretise()

# create an algorithm from the discretised computations
alg = TraditionalAlgorithmRK(block)

# set the simulation data type, for more information on the datatypes see opensbli.core.datatypes
SimulationDataType.set_datatype(Double)

# Write the code for the algorithm
OPSC(alg)
# Change grid size here if desired
f = h5py.File('grid.h5', 'r')
x0, x1 = f['x0'].value, f['x1'].value
print(x1.shape)
npoints = [357, 179]
halos = [(-5, 5), (-5, 5)]
arrays, array_names = [x0, x1], ['x0', 'x1']
output_hdf5(arrays, array_names, halos, npoints, block)
# Simulation parameters
constants = ['Re', 'gama', 'Minf', 'Pr', 'dt', 'niter', 'block0np0', 'block0np1', 'Delta0block0', 'Delta1block0']
values = ['100.0', '1.4', '0.1', '0.71', '0.0001', '100', '357', '179', '120.0/(block0np0-1)', '120.0/(block0np1-1)']
substitute_simulation_parameters(constants, values)
print_iteration_ops(NaN_check='rho_B0')