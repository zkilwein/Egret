#  ___________________________________________________________________________
#
#  EGRET: Electrical Grid Research and Engineering Tools
#  Copyright 2019 National Technology & Engineering Solutions of Sandia, LLC
#  (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
#  Government retains certain rights in this software.
#  This software is distributed under the Revised BSD License.
#  ___________________________________________________________________________

'''
 Tests linear OPF models against the ACOPF
 Usage:
    -python test_approximations --test_casesX
        Runs main() method

 Output functions:
    -solve_approximation_models(test_case, test_model_dict, init_min=0.9, init_max=1.1, steps=10)
        test_case: str, name of input data matpower file in pglib-opf-master
        test_model_dict: dict, list of models (key) and True/False (value) for which formulations/settings to
            run in the inner_loop_solves() method
        init_min: float (scalar), smallest demand multiplier to test approximation model. May be increased if
            ACOPF is infeasible
        init_max: float (scalar), largest demand multiplier to test approximation model. May be decreased if
            ACOPF is infeasible
        steps: integer, number of steps taken between init_min and init_max. Total of steps+1 model solves.
    -generate_sensitivity_plot(test_case,test_model_dict, data_generator=X)
        test_case: str, plots data from a test_case*.json wildcard search
        test_model_dict: dict, list of models (key) and True/False (value) for which formulations/settings to plot
        data_generator: function (perhaps from tx_utils.py) to pull data from JSON files
    -generate_pareto_plot(test_case, test_model_dict, y_axis_generator=Y, x_axis_generator=X, size_generator=None)
        test_case: str, plots data from a test_case*.json wildcard search
        test_model_dict: dict, list of models (key) and True/False (value) for which formulations/settings to plot
        y_axis_generator: function (perhaps from test_utils.py) to pull y-axis data from JSON files
        x_axis_generator: function (perhaps from test_utils.py) to pull x-axis data from JSON files
        size_generator: function (perhaps from test_utils.py) to pull dot size data from JSON files


 test_utils (tu) generator functions:
    *solve_time*
    *num_constraints*
    num_variables
    num_nonzeros
    model_sparsity
    total_cost
    ploss
    qloss
    pgen
    qgen
    pflow
    qflow
    vmag
    *sum_infeas*
    kcl_p_infeas
    kcl_q_infeas
    thermal_infeas
    avg_kcl_p_infeas
    avg_kcl_q_infeas
    avg_thermal_infeas
    max_kcl_p_infeas
    max_kcl_q_infeas
    max_thermal_infeas


'''

import os, shutil, glob, json
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.cm as cmap
from cycler import cycler
import math
import unittest
import egret.data.test_utils as tu
from pyomo.opt import SolverFactory, TerminationCondition
from egret.models.acopf import *
from egret.models.ccm import *
from egret.models.fdf import *
from egret.models.fdf_simplified import *
from egret.models.lccm import *
from egret.models.dcopf_losses import *
from egret.models.dcopf import *
from egret.models.copperplate_dispatch import *
from egret.data.model_data import ModelData
from parameterized import parameterized
from egret.parsers.matpower_parser import create_ModelData
from os import listdir
from os.path import isfile, join

current_dir = os.path.dirname(os.path.abspath(__file__))
# test_cases = [join('../../../download/pglib-opf-master/', f) for f in listdir('../../../download/pglib-opf-master/') if isfile(join('../../../download/pglib-opf-master/', f)) and f.endswith('.m')]
case_names = ['pglib_opf_case3_lmbd',
              'pglib_opf_case5_pjm',
              'pglib_opf_case14_ieee',
              'pglib_opf_case24_ieee_rts',
              'pglib_opf_case30_as',
              'pglib_opf_case30_fsr',
              'pglib_opf_case30_ieee',
              'pglib_opf_case39_epri',
              'pglib_opf_case57_ieee',
              'pglib_opf_case73_ieee_rts',
              'pglib_opf_case89_pegase', ### not feasible at mult = 1.01 ###
              'pglib_opf_case118_ieee',
              'pglib_opf_case162_ieee_dtc',
              'pglib_opf_case179_goc',
              'pglib_opf_case200_tamu',
              'pglib_opf_case240_pserc',
              'pglib_opf_case300_ieee',
              'pglib_opf_case500_tamu',
              'pglib_opf_case588_sdet',
              'pglib_opf_case1354_pegase',
              'pglib_opf_case1888_rte',
              'pglib_opf_case1951_rte',
              'pglib_opf_case2000_tamu',
              'pglib_opf_case2316_sdet',
              'pglib_opf_case2383wp_k',
              'pglib_opf_case2736sp_k',
              'pglib_opf_case2737sop_k',
              'pglib_opf_case2746wop_k',
              'pglib_opf_case2746wp_k',
              'pglib_opf_case2848_rte',
              'pglib_opf_case2853_sdet',
              'pglib_opf_case2868_rte',
              'pglib_opf_case2869_pegase',
              'pglib_opf_case3012wp_k',
              'pglib_opf_case3120sp_k',
              'pglib_opf_case3375wp_k',
              'pglib_opf_case4661_sdet',
              'pglib_opf_case6468_rte',
              'pglib_opf_case6470_rte',
              'pglib_opf_case6495_rte',
              'pglib_opf_case6515_rte',
              'pglib_opf_case9241_pegase',
              'pglib_opf_case10000_tamu',
              'pglib_opf_case13659_pegase',
              ]
test_cases = [join('../../download/pglib-opf-master/', f + '.m') for f in case_names]
#test_cases = [os.path.join(current_dir, 'download', 'pglib-opf-master', '{}.m'.format(i)) for i in case_names]




def set_acopf_basepoint_min_max(md_dict, init_min=0.9, init_max=1.1, **kwargs):
    """
    returns AC basepoint solution and feasible min/max range
     - new min/max range b/c test case may not be feasible in [init_min to init_max]
    """
    md = md_dict.clone_in_service()
    loads = dict(md.elements(element_type='load'))

    acopf_model = create_psv_acopf_model

    md_basept, m, results = solve_acopf(md, "ipopt", acopf_model_generator=acopf_model, return_model=True,
                                        return_results=True, solver_tee=False)

    # exit if base point does not return optimal
    if not results.solver.termination_condition == TerminationCondition.optimal:
        raise Exception('Base case acopf did not return optimal solution')

    # find feasible min and max demand multipliers
    else:
        mult_min = multiplier_loop(md, init=init_min, steps=10, acopf_model=acopf_model)
        mult_max = multiplier_loop(md, init=init_max, steps=10, acopf_model=acopf_model)

    return md_basept, mult_min, mult_max


def multiplier_loop(model_data, init=0.9, steps=10, acopf_model=create_psv_acopf_model):
    '''
    init < 1 searches for the lowest demand multiplier >= init that has an optimal acopf solution
    init > 1 searches for the highest demand multiplier <= init that has an optimal acopf solution
    steps determines the increments in [init, 1] where the search is made
    '''

    md = model_data.clone_in_service()

    loads = dict(md.elements(element_type='load'))

    # step size
    inc = abs(1 - init) / steps

    # initial loads
    init_p_loads = {k: loads[k]['p_load'] for k in loads.keys()}
    init_q_loads = {k: loads[k]['q_load'] for k in loads.keys()}

    # loop
    final_mult = None
    for step in range(0, steps):

        # for finding minimum
        if init < 1:
            mult = round(init - step * inc, 4)

        # for finding maximum
        elif init > 1:
            mult = round(init - step * inc, 4)

        # adjust load from init_min
        for k in loads.keys():
            loads[k]['p_load'] = init_p_loads[k] * mult
            loads[k]['q_load'] = init_q_loads[k] * mult

        try:
            md_, results = solve_acopf(md, "ipopt", acopf_model_generator=acopf_model, return_model=False,
                                       return_results=True, solver_tee=False)
            final_mult = mult
            print('mult={} has an acceptable solution.'.format(mult))
            break

        except Exception:
            print('mult={} raises an error. Continuing search.'.format(mult))

    if final_mult is None:
        print('Found no acceptable solutions with mult != 1. Try init between 1 and {}.'.format(mult))
        final_mult = 1

    return final_mult


def create_new_model_data(model_data, mult):
    md = model_data.clone_in_service()

    loads = dict(md.elements(element_type='load'))

    # initial loads
    init_p_loads = {k: loads[k]['p_load'] for k in loads.keys()}
    init_q_loads = {k: loads[k]['q_load'] for k in loads.keys()}

    # multiply loads
    for k in loads.keys():
        loads[k]['p_load'] = init_p_loads[k] * mult
        loads[k]['q_load'] = init_q_loads[k] * mult

    return md


def inner_loop_solves(md_basepoint, md_flat, mult, test_model_dict):
    '''
    solve models in test_model_dict (ideally, only one model is passed here)
    loads are multiplied by mult
    sensitivities from md_basepoint or md_flat as appropriate for the model being solved
    '''

    tm = test_model_dict

    if tm['acopf']:
        md = create_new_model_data(md_flat, mult)
        try:
            md_ac, m, results = solve_acopf(md, "ipopt", return_model=True, return_results=True, solver_tee=False)
            record_results('acopf', mult, md_ac)
        except:
            pass

    if tm['slopf']:
        md = create_new_model_data(md_basepoint, mult)
        try:
            md_lccm, m, results = solve_lccm(md, "gurobi", return_model=True, return_results=True, solver_tee=False)
            record_results('slopf', mult, md_lccm)
        except:
            pass

    if tm['dlopf_default']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        ptdf_options = {}
        ptdf_options['lazy'] = False
        ptdf_options['lazy_voltage'] = False
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdf, m, results = solve_fdf(md, "gurobi", return_model=True, return_results=True,
                                           solver_tee=False, **kwargs)
            record_results('dlopf_default', mult, md_fdf)
        except:
            pass

    if tm['dlopf_lazy']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        options = {}
        options['method'] = 1
        ptdf_options = {}
        ptdf_options['lazy'] = True
        ptdf_options['lazy_voltage'] = True
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdf, m, results = solve_fdf(md, "gurobi_persistent", return_model=True, return_results=True,
                                           solver_tee=False, options=options, **kwargs)
            record_results('dlopf_lazy', mult, md_fdf)
        except:
            pass

    if tm['dlopf_e4']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        options = {}
        options['method'] = 1
        ptdf_options = {}
        ptdf_options['lazy'] = True
        ptdf_options['lazy_voltage'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-4
        ptdf_options['abs_qtdf_tol'] = 5e-4
        ptdf_options['rel_vdf_tol'] = 10e-4
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdf, m, results = solve_fdf(md, "gurobi_persistent", return_model=True, return_results=True,
                                           solver_tee=False, options=options, **kwargs)
            record_results('dlopf_e4', mult, md_fdf)
        except:
            pass

    if tm['dlopf_e3']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        options = {}
        options['method'] = 1
        ptdf_options = {}
        ptdf_options['lazy'] = True
        ptdf_options['lazy_voltage'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-3
        ptdf_options['abs_qtdf_tol'] = 5e-3
        ptdf_options['rel_vdf_tol'] = 10e-3
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdf, m, results = solve_fdf(md, "gurobi_persistent", return_model=True, return_results=True,
                                           solver_tee=False, options=options, **kwargs)
            record_results('dlopf_e3', mult, md_fdf)
        except:
            pass

    if tm['dlopf_e2']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        options = {}
        options['method'] = 1
        ptdf_options = {}
        ptdf_options['lazy'] = True
        ptdf_options['lazy_voltage'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-2
        ptdf_options['abs_qtdf_tol'] = 5e-2
        ptdf_options['rel_vdf_tol'] = 10e-2
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdf, m, results = solve_fdf(md, "gurobi_persistent", return_model=True, return_results=True,
                                           solver_tee=False, options=options, **kwargs)
            record_results('dlopf_e2', mult, md_fdf)
        except:
            pass

    if tm['clopf_default']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        ptdf_options = {}
        ptdf_options['lazy'] = False
        ptdf_options['lazy_voltage'] = False
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdfs, m, results = solve_fdf_simplified(md, "gurobi", return_model=True, return_results=True,
                                                       solver_tee=False, **kwargs)
            record_results('clopf_default', mult, md_fdfs)
        except:
            pass

    if tm['clopf_lazy']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        options = {}
        options['method'] = 1
        ptdf_options = {}
        ptdf_options['lazy'] = True
        ptdf_options['lazy_voltage'] = True
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdfs, m, results = solve_fdf_simplified(md, "gurobi_persistent", return_model=True, return_results=True,
                                                       solver_tee=False, options=options, **kwargs)
            record_results('clopf_lazy', mult, md_fdfs)
        except:
            pass

    if tm['clopf_e4']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        options = {}
        options['method'] = 1
        ptdf_options = {}
        ptdf_options['lazy'] = True
        ptdf_options['lazy_voltage'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-4
        ptdf_options['abs_qtdf_tol'] = 5e-4
        ptdf_options['rel_vdf_tol'] = 10e-4
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdfs, m, results = solve_fdf_simplified(md, "gurobi_persistent", return_model=True, return_results=True,
                                                       solver_tee=False, options=options, **kwargs)
            record_results('clopf_e4', mult, md_fdfs)
        except:
            pass

    if tm['clopf_e3']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        options = {}
        options['method'] = 1
        ptdf_options = {}
        ptdf_options['lazy'] = True
        ptdf_options['lazy_voltage'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-3
        ptdf_options['abs_qtdf_tol'] = 5e-3
        ptdf_options['rel_vdf_tol'] = 10e-3
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdfs, m, results = solve_fdf_simplified(md, "gurobi_persistent", return_model=True, return_results=True,
                                                       solver_tee=False, options=options, **kwargs)
            record_results('clopf_e3', mult, md_fdfs)
        except:
            pass

    if tm['clopf_e2']:
        md = create_new_model_data(md_basepoint, mult)
        kwargs = {}
        options = {}
        options['method'] = 1
        ptdf_options = {}
        ptdf_options['lazy'] = True
        ptdf_options['lazy_voltage'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-2
        ptdf_options['abs_qtdf_tol'] = 5e-2
        ptdf_options['rel_vdf_tol'] = 10e-2
        kwargs['ptdf_options'] = ptdf_options
        try:
            md_fdfs, m, results = solve_fdf_simplified(md, "gurobi_persistent", return_model=True, return_results=True,
                                                       solver_tee=False, options=options, **kwargs)
            record_results('clopf_e2', mult, md_fdfs)
        except:
            pass

    if tm['clopf_p_default']:
        kwargs = {}
        ptdf_options = {}
        ptdf_options['lazy'] = False
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_basepoint, mult)
        try:
            md_ptdfl, m, results = solve_dcopf_losses(md, "gurobi",
                                                      dcopf_losses_model_generator=create_ptdf_losses_dcopf_model,
                                                      return_model=True, return_results=True, solver_tee=False, **kwargs)
            record_results('clopf_p_default', mult, md_ptdfl)
        except:
            pass

    if tm['clopf_p_lazy']:
        kwargs = {}
        ptdf_options = {}
        options = {}
        options['method'] = 1
        ptdf_options['lazy'] = True
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_basepoint, mult)
        try:
            md_ptdfl, m, results = solve_dcopf_losses(md, "gurobi_persistent",
                                                      dcopf_losses_model_generator=create_ptdf_losses_dcopf_model,
                                                      return_model=True, return_results=True, solver_tee=False,
                                                      options=options, **kwargs)
            record_results('clopf_p_lazy', mult, md_ptdfl)
        except:
            pass

    if tm['clopf_p_e4']:
        kwargs = {}
        ptdf_options = {}
        options = {}
        options['method'] = 1
        ptdf_options['lazy'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-4
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_basepoint, mult)
        try:
            md_ptdfl, m, results = solve_dcopf_losses(md, "gurobi_persistent",
                                                      dcopf_losses_model_generator=create_ptdf_losses_dcopf_model,
                                                      return_model=True, return_results=True, solver_tee=False,
                                                      options=options, **kwargs)
            record_results('clopf_p_e4', mult, md_ptdfl)
        except:
            pass

    if tm['clopf_p_e3']:
        kwargs = {}
        ptdf_options = {}
        options = {}
        options['method'] = 1
        ptdf_options['lazy'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-3
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_basepoint, mult)
        try:
            md_ptdfl, m, results = solve_dcopf_losses(md, "gurobi_persistent",
                                                      dcopf_losses_model_generator=create_ptdf_losses_dcopf_model,
                                                      return_model=True, return_results=True, solver_tee=False,
                                                      options=options, **kwargs)
            record_results('clopf_p_e3', mult, md_ptdfl)
        except:
            pass

    if tm['clopf_p_e2']:
        kwargs = {}
        ptdf_options = {}
        options = {}
        options['method'] = 1
        ptdf_options['lazy'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-2
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_basepoint, mult)
        try:
            md_ptdfl, m, results = solve_dcopf_losses(md, "gurobi_persistent",
                                                      dcopf_losses_model_generator=create_ptdf_losses_dcopf_model,
                                                      return_model=True, return_results=True, solver_tee=False,
                                                      options=options, **kwargs)
            record_results('clopf_p_e2', mult, md_ptdfl)
        except:
            pass

    if tm['dcopf_ptdf_default']:
        kwargs = {}
        ptdf_options = {}
        ptdf_options['lazy'] = False
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_flat, mult)
        try:
            md_ptdf, m, results = solve_dcopf(md, "gurobi", dcopf_model_generator=create_ptdf_dcopf_model,
                                              return_model=True, return_results=True, solver_tee=False, **kwargs)
            record_results('dcopf_ptdf_default', mult, md_ptdf)
        except:
            pass

    if tm['dcopf_ptdf_lazy']:
        kwargs = {}
        ptdf_options = {}
        options = {}
        options['method'] = 1
        ptdf_options['lazy'] = True
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_flat, mult)
        try:
            md_ptdf, m, results = solve_dcopf(md, "gurobi_persistent", dcopf_model_generator=create_ptdf_dcopf_model,
                                              return_model=True, return_results=True, solver_tee=False,
                                              options=options, **kwargs)
            record_results('dcopf_ptdf_lazy', mult, md_ptdf)
        except:
            pass

    if tm['dcopf_ptdf_e4']:
        kwargs = {}
        ptdf_options = {}
        options = {}
        options['method'] = 1
        ptdf_options['lazy'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-4
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_flat, mult)
        try:
            md_ptdf, m, results = solve_dcopf(md, "gurobi_persistent", dcopf_model_generator=create_ptdf_dcopf_model,
                                              return_model=True, return_results=True, solver_tee=False,
                                              options=options, **kwargs)
            record_results('dcopf_ptdf_e4', mult, md_ptdf)
        except:
            pass

    if tm['dcopf_ptdf_e3']:
        kwargs = {}
        ptdf_options = {}
        options = {}
        options['method'] = 1
        ptdf_options['lazy'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-3
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_flat, mult)
        try:
            md_ptdf, m, results = solve_dcopf(md, "gurobi_persistent", dcopf_model_generator=create_ptdf_dcopf_model,
                                              return_model=True, return_results=True, solver_tee=False,
                                              options=options, **kwargs)
            record_results('dcopf_ptdf_e3', mult, md_ptdf)
        except:
            pass

    if tm['dcopf_ptdf_e2']:
        kwargs = {}
        ptdf_options = {}
        options = {}
        options['method'] = 1
        ptdf_options['lazy'] = True
        ptdf_options['abs_ptdf_tol'] = 1e-2
        kwargs['ptdf_options'] = ptdf_options
        md = create_new_model_data(md_flat, mult)
        try:
            md_ptdf, m, results = solve_dcopf(md, "gurobi_persistent", dcopf_model_generator=create_ptdf_dcopf_model,
                                              return_model=True, return_results=True, solver_tee=False,
                                              options=options, **kwargs)
            record_results('dcopf_ptdf_e2', mult, md_ptdf)
        except:
            pass

    if tm['qcopf_btheta']:
        md = create_new_model_data(md_flat, mult)
        try:
            md_bthetal, m, results = solve_dcopf_losses(md, "gurobi",
                                                        dcopf_losses_model_generator=create_btheta_losses_dcopf_model,
                                                        return_model=True, return_results=True, solver_tee=False)
            record_results('qcopf_btheta', mult, md_bthetal)
        except:
            pass

    if tm['dcopf_btheta']:
        md = create_new_model_data(md_flat, mult)
        try:
            md_btheta, m, results = solve_dcopf(md, "gurobi", dcopf_model_generator=create_btheta_dcopf_model,
                                                return_model=True, return_results=True, solver_tee=False)
            record_results('dcopf_btheta', mult, md_btheta)
        except:
            pass


def record_results(idx, mult, md):
    '''
    writes model data (md) object to .json file
    '''

    data_utils_deprecated.destroy_dicts_of_fdf(md)

    filename = md.data['system']['model_name'] + '_' + idx + '_{0:04.0f}'.format(mult * 1000)
    md.data['system']['mult'] = mult
    md.data['system']['filename'] = filename

    md.write_to_json(filename)
    print('...out: {}'.format(filename))


def get_solution_file_location(test_case):
    _, case = os.path.split(test_case)
    case, _ = os.path.splitext(case)
    current_dir, current_file = os.path.split(os.path.realpath(__file__))
    solution_location = os.path.join(current_dir, 'transmission_test_instances', 'approximation_solution_files', case)

    return solution_location


def get_summary_file_location(folder):
    current_dir, current_file = os.path.split(os.path.realpath(__file__))
    location = os.path.join(current_dir, 'transmission_test_instances','approximation_summary_files', folder)

    if not os.path.exists(location):
        os.makedirs(location)

    return location


def create_testcase_directory(test_case):
    # directory locations
    cwd = os.getcwd()
    case_folder, case = os.path.split(test_case)
    case, ext = os.path.splitext(case)
    current_dir, current_file = os.path.split(os.path.realpath(__file__))

    # move to case directory
    source = os.path.join(cwd, case + '_*.json')
    destination = get_solution_file_location(test_case)

    if not os.path.exists(destination):
        os.makedirs(destination)

    if not glob.glob(source):
        print('No files to move.')
    else:
        print('dest: {}'.format(destination))

        for src in glob.glob(source):
            print('src:  {}'.format(src))
            folder, file = os.path.split(src)
            dest = os.path.join(destination, file)  # full destination path will overwrite existing files
            shutil.move(src, dest)

    return destination


def read_sensitivity_data(case_folder, test_model, data_generator=tu.total_cost):
    parent, case = os.path.split(case_folder)
    filename = case + "_" + test_model + "_*.json"
    file_list = glob.glob(os.path.join(case_folder, filename))

    data_type = data_generator.__name__

    print("Reading " + data_type + " data from " + filename + ".")

    data = {}
    for file in file_list:
        md_dict = json.load(open(file))
        md = ModelData(md_dict)
        mult = md.data['system']['mult']
        data[mult] = data_generator(md)

    data_is_vector = False
    for d in data:
        data_is_vector = hasattr(data[d], "__len__")

    if data_is_vector:
        df_data = pd.DataFrame(data)
        df_data = df_data.sort_index(axis=1)
        # print('data: {}'.format(df_data))
    else:
        df_data = pd.DataFrame(data, index=[test_model])
        # df_data = df_data.transpose()
        df_data = df_data.sort_index(axis=1)
        # print('data: {}'.format(df_data))

    return df_data


def solve_approximation_models(test_case, test_model_dict, init_min=0.9, init_max=1.1, steps=20):
    '''
    1. initialize base case and demand range
    2. loop over demand values
    3. record results to .json files
    '''

    md_flat = create_ModelData(test_case)

    md_basept, min_mult, max_mult = set_acopf_basepoint_min_max(md_flat, init_min, init_max)
    test_model_dict['acopf'] = True

    ## put the sensitivities into modeData so they don't need to be recalculated for each model
    data_utils_deprecated.create_dicts_of_fdf_simplified(md_basept)
    data_utils_deprecated.create_dicts_of_ptdf(md_flat)

    inc = (max_mult - min_mult) / steps

    for step in range(0, steps + 1):
        mult = round(min_mult + step * inc, 4)

        inner_loop_solves(md_basept, md_flat, mult, test_model_dict)

    create_testcase_directory(test_case)


def geometricMean(array):

    geomean = list()

    for row in array:
        n = len(row)
        sum = 0
        for i in range(n):
            sum += math.log(row[i])
        sum = sum / n
        gm = math.exp(sum)
        geomean.append(gm)

    return geomean


def generate_mean_data(test_case, test_model_dict, function_list=[tu.num_buses,tu.num_constraints,tu.sum_infeas,tu.solve_time]):

    case_location = get_solution_file_location(test_case)
    src_folder, case_name = os.path.split(test_case)
    case_name, ext = os.path.splitext(case_name)

    ## include acopf results
    test_model_dict['acopf'] = True

    df_data = pd.DataFrame(data=None, index=test_model_dict.keys())

    for func in function_list:
        ## put data into blank DataFrame
        df_func = pd.DataFrame(data=None)

        for test_model, val in test_model_dict.items():
            # read data and place in df_func
            df_raw = read_sensitivity_data(case_location, test_model, data_generator=func)
            df_func = pd.concat([df_func , df_raw], sort=True)

        func_name = func.__name__

        ## also calculate geomean and maximum if function is solve_time()
        if func_name=='solve_time':
            gm = geometricMean(df_func.to_numpy())
            gm_name = func_name + '_geomean'
            df_gm = pd.DataFrame(data=gm, index=df_func.index, columns=[gm_name])
            df_data[gm_name] = df_gm

            max = df_func.max(axis=1)
            max_name = func_name + '_max'
            df_max = pd.DataFrame(data=max.values, index=df_func.index, columns=['max_' + func_name])
            df_data[max_name] = df_max

            func_name = func_name + '_avg'


        df_func = df_func.mean(axis=1)
        df_func = pd.DataFrame(data=df_func.values, index=df_func.index, columns=[func_name])

        #df_data = pd.concat([df_data, df_func])
        df_data[func_name] = df_func

    ## save DATA to csv
    destination = get_summary_file_location('data')
    filename = "mean_data_" + case_name + ".csv"
    df_data.to_csv(os.path.join(destination, filename))


def generate_sensitivity_data(test_case, test_model_dict, data_generator=tu.sum_infeas,
                              data_is_pct=False, data_is_vector=False, vector_norm=2):

    case_location = get_solution_file_location(test_case)
    src_folder, case_name = os.path.split(test_case)
    case_name, ext = os.path.splitext(case_name)

    # acopf comparison
    df_acopf = read_sensitivity_data(case_location, 'acopf', data_generator=data_generator)


    ## calculates specified L-norm of difference with acopf (e.g., generator dispatch, branch flows, voltage profile...)
    if data_is_vector:
        print('data is vector of length {}'.format(len(df_acopf.values)))

    ## calcuates relative difference from acopf (e.g., objective value, solution time...)
    elif data_is_pct:
        acopf_avg = sum(df_acopf[idx].values for idx in df_acopf) / len(df_acopf)
        print('data is pct with acopf values averaging {}'.format(acopf_avg))
    else:
        acopf_avg = sum(df_acopf[idx].values for idx in df_acopf) / len(df_acopf)
        print('data is nominal with acopf values averaging {}'.format(acopf_avg))

    # empty dataframe to add data into
    df_data = pd.DataFrame(data=None)

    # iterate over test_model's
    test_model_dict['acopf'] = True
    for test_model, val in test_model_dict.items():
        if val:
            df_approx = read_sensitivity_data(case_location, test_model, data_generator=data_generator)

            # calculate norm from df_diff columns
            data = {}
            avg_ac_data = sum(df_acopf[idx].values for idx in df_acopf) / len(df_acopf)
            for col in df_approx:
                if data_is_vector is True:
                    data[col] = np.linalg.norm(df_approx[col].values - df_acopf[col].values, vector_norm)
                elif data_is_pct is True:
                    data[col] = ((df_approx[col].values - df_acopf[col].values) / df_acopf[col].values) * 100
                else:
                    data[col] = df_approx[col].values

            # record test_model column in DataFrame
            df_col = pd.DataFrame(data, index=[test_model])
            df_data = pd.concat([df_data, df_col], sort=True)


    ## save DATA as csv
    y_axis_data = data_generator.__name__
    df_data = df_data.T
    destination = get_summary_file_location('data')
    filename = "sensitivity_data_" + case_name + "_" + y_axis_data + ".csv"
    df_data.to_csv(os.path.join(destination, filename))



def get_data(filename, test_model_dict):

    ## get data from CSV
    source = get_summary_file_location('data')
    df_data = pd.read_csv(os.path.join(source,filename), index_col=0)

    remove_list = []
    for tm,val in test_model_dict.items():
        if not val:
            remove_list.append(tm)

    try:
        df_data = df_data.drop(remove_list, axis=0)
    except:
        df_data = df_data.drop(remove_list, axis=1)

    return df_data

def generate_pareto_plot(test_case, test_model_dict, y_data='sum_infeas', x_data='solve_time', y_units='p.u', x_units='s',
                         mark_default='o', mark_lazy='D', mark_acopf='*', mark_size=36, colors=cmap.viridis,
                         annotate_plot=False, show_plot=False):

    ## get data
    _, case_name = os.path.split(test_case)
    case_name, ext = os.path.splitext(case_name)
    input = "mean_data_" + case_name + ".csv"
    df_data = get_data(input, test_model_dict)

    models = list(df_data.index.values)
    df_y_data = df_data[y_data]
    df_x_data = df_data[x_data]


    ## assign color values
    num_entries = len(df_data)
    color = colors(np.linspace(0, 1, num_entries))
    custom_cycler = (cycler(color=color))
    plt.rc('axes', prop_cycle=custom_cycler)


    fig, ax = plt.subplots()
    for m in models:
        if 'lazy' in m:
            mark = mark_lazy
        elif 'acopf' in m:
            mark = mark_acopf
        else:
            mark = mark_default

        x = df_x_data[m]
        y = df_y_data[m]
        ax.scatter(x, y, s=mark_size, label=m, marker=mark)

        if annotate_plot:
            ax.annotate(m, (x,y))

    ax.set_title(y_data + " vs. " + x_data + "\n(" + case_name + ")")
    ax.set_ylabel(y_data + " (" + y_units + ")")
    ax.set_xlabel(x_data + " (" + x_units + ")")

    box = ax.get_position()
    ax.set_position([box.x0, box.y0, 0.8 * box.width, box.height])
    ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))

    ## save FIGURE to png
    figure_dest = get_summary_file_location('figures')
    filename = "paretoplot_" + case_name + "_" + y_data + "_v_" + x_data + ".png"
    plt.savefig(os.path.join(figure_dest, filename))

    if show_plot:
        plt.show()



def generate_sensitivity_plot(test_case, test_model_dict, plot_data='sum_infeas', units='p.u.',
                              colors=cmap.viridis, show_plot=False):

    ## get data
    _, case_name = os.path.split(test_case)
    case_name, ext = os.path.splitext(case_name)
    input = "sensitivity_data_" + case_name + "_" + plot_data + ".csv"
    df_data = get_data(input, test_model_dict)

    models = list(df_data.columns.values)

    ## assign color values
    num_entries = len(df_data.columns)
    color = colors(np.linspace(0, 1, num_entries))
    custom_cycler = (cycler(color=color))
    plt.rc('axes', prop_cycle=custom_cycler)

    # show data in graph
    fig, ax = plt.subplots()
    for m in models:
        if m =='slopf':
            mark = '>'
        elif m == 'dlopf_default':
            mark = '^'
        elif m == 'clopf_default':
            mark = 'v'
        elif m == 'clopf_p_default':
            mark = '^'
        elif m == 'qcopf_btheta':
            mark = 'v'
        elif m == 'dcopf_ptdf_default':
            mark = '^'
        elif m == 'dcopf_btheta':
            mark = 'v'
        else:
            mark = ''
        y = df_data[m]
        ax.plot(y, label=m, marker=mark)


    ax.set_title(plot_data + " (" + case_name + ")")
    # output.set_ylim(top=0)
    ax.set_xlabel("Demand Multiplier")

    box = ax.get_position()
    ax.set_position([box.x0, box.y0, 0.8 * box.width, box.height])
    ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))

    filename = "sensitivityplot_" + case_name + "_" + plot_data + ".png"
    ax.set_ylabel(plot_data + " (" +  units + ")")

    ## save FIGURE as png
    destination = get_summary_file_location('figures')
    plt.savefig(os.path.join(destination, filename))

    # display
    if show_plot is True:
        plt.show()


def generate_case_size_plot(test_model_dict, case_list=case_names,
                            y_data='solve_time_geomean', y_units='s', x_data = 'num_buses', x_units=None,
                            s_data='num_constraints', colors=cmap.viridis, max_size=500, min_size=5,
                            annotate_plot=False, show_plot=False):

    ## TODO: separate color/size legends
    ## TODO: loglog scale

    ## get data
    y_dict = {}
    x_dict = {}
    s_dict = {}
    for case in case_list:
        try:
            input = "mean_data_" + case + ".csv"
            df_data = get_data(input, test_model_dict)
            models = list(df_data.index.values)
            for m in models:
                if m in y_dict:
                    y_dict[m].append(df_data.at[m, y_data])
                    x_dict[m].append(df_data.at[m, x_data])
                    if s_data is not None:
                        s_dict[m].append(df_data.at[m, s_data])
                else:
                    y_dict[m] = [df_data.at[m, y_data]]
                    x_dict[m] = [df_data.at[m, x_data]]
                    if s_data is not None:
                        s_dict[m] = [df_data.at[m, s_data]]

        except:
            pass

    df_y_data = pd.DataFrame(y_dict)
    df_x_data = pd.DataFrame(x_dict)
#    if s_data is not None:
    df_s_data = pd.DataFrame(s_dict)


    ## assign color values
    num_entries = len(df_data)
    color = colors(np.linspace(0, 1, num_entries))
    custom_cycler = (cycler(color=color))
    plt.rc('axes', prop_cycle=custom_cycler)


    fig, ax = plt.subplots()
    for m in models:

        x = df_x_data[m]
        y = df_y_data[m]
        if s_data is None:
            mark_size = None
        else:
            mark_size = df_s_data[m]
        ax.scatter(x, y, s=mark_size, label=m)

        if annotate_plot:
            ax.annotate(m, (x,y))

    ax.set_title(y_data + " vs. " + x_data)
    if y_units is not None:
        ax.set_ylabel(y_data + " (" + y_units + ")")
    else:
        ax.set_ylabel(y_data)
    if x_units is not None:
        ax.set_xlabel(x_data + " (" + x_units + ")")
    else:
        ax.set_xlabel(x_data)

    box = ax.get_position()
    ax.set_position([box.x0, box.y0, 0.8 * box.width, box.height])
    ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))

    ## save FIGURE to png
    figure_dest = get_summary_file_location('figures')
    filename = "casesizeplot_" + y_data + "_v_" + x_data + ".png"
    plt.savefig(os.path.join(figure_dest, filename))

    if show_plot:
        plt.show()



def main(arg):

    idxA = case_names.index('pglib_opf_case1354_pegase')  ## < 1000 buses
    idxB = case_names.index('pglib_opf_case2383wp_k')  ## 1354 - 2316 buses
    idxC = case_names.index('pglib_opf_case6468_rte')  ## 2383 - 4661 buses
    idxD = case_names.index('pglib_opf_case13659_pegase')  ## 6468 - 10000 buses
    idxE = case_names.index('pglib_opf_case13659_pegase') + 1  ## 13659 buses

    if arg == 'A':
        idx_list = list(range(9,idxA))
    elif arg == 'B':
        idx_list = list(range(idxA,idxB))
    elif arg == 'C':
        idx_list = list(range(idxB,idxC))
    elif arg == 'D':
        idx_list = list(range(idxC,idxD))
    elif arg == 'E':
        idx_list = list(range(idxD,idxE))

    for idx in idx_list:
        submain(idx, show_plot=False)


def submain(idx=None, show_plot=True):
    """
    solves models and generates plots for test case at test_cases[idx] or a default case
    """

    ## Sequential colors: lightness value increases monotonically
    #colors = cmap.viridis #*****#
    #colors = cmap.cividis
    #colors = cmap.magma
    #colors = cmap.plasma #*****#
    ## Diverging/cyclic colors: monotonically increasing lightness followed by monotonically decreasing lightness
    #colors = cmap.Spectral #*****#
    #colors = cmap.coolwarm #*****#
    #colors = cmap.twilight
    #colors = cmap.twilight_shifted
    #colors = cmap.hsv
    ## Qualitative colors: not perceptual
    #colors = cmap.Paired
    #colors = cmap.Accent
    #colors = cmap.Set3
    ## Miscellaneous colors:
    colors = cmap.gnuplot #*****#
    #colors = cmap.jet
    #colors = cmap.nipy_spectral #*****#



    if idx is None:
        test_case = join('../../download/pglib-opf-master/', 'pglib_opf_case3_lmbd.m')
#        test_case = join('../../download/pglib-opf-master/', 'pglib_opf_case5_pjm.m')
#        test_case = join('../../download/pglib-opf-master/', 'pglib_opf_case30_ieee.m')
#        test_case = join('../../download/pglib-opf-master/', 'pglib_opf_case24_ieee_rts.m')
#        test_case = join('../../download/pglib-opf-master/', 'pglib_opf_case118_ieee.m')
#        test_case = join('../../download/pglib-opf-master/', 'pglib_opf_case300_ieee.m')
    else:
        test_case=idx_to_test_case(idx)

    test_model_dict = \
        {'acopf' : True,
         'slopf': True,
         'dlopf_default': True,
         'dlopf_lazy' : True,
         'dlopf_e4': True,
         'dlopf_e3': True,
         'dlopf_e2': True,
         'clopf_default': True,
         'clopf_lazy': True,
         'clopf_e4': True,
         'clopf_e3': True,
         'clopf_e2': True,
         'clopf_p_default': True,
         'clopf_p_lazy': True,
         'clopf_p_e4': True,
         'clopf_p_e3': True,
         'clopf_p_e2': True,
         'qcopf_btheta': True,
         'dcopf_ptdf_default': True,
         'dcopf_ptdf_lazy': True,
         'dcopf_ptdf_e4': True,
         'dcopf_ptdf_e3': True,
         'dcopf_ptdf_e2': True,
         'dcopf_btheta': True
         }
    mean_functions = [tu.num_buses,
                      tu.num_branches,
                      tu.num_constraints,
                      tu.num_variables,
                      tu.model_sparsity,
                      tu.sum_infeas,
                      tu.solve_time,
                      tu.thermal_infeas,
                      tu.kcl_p_infeas,
                      tu.kcl_q_infeas,
                      tu.max_thermal_infeas,
                      tu.max_kcl_p_infeas,
                      tu.max_kcl_q_infeas,
                      ]

    ## Model solves
    #solve_approximation_models(test_case, test_model_dict, init_min=0.9, init_max=1.1, steps=20)

    ## Generate data files
#    generate_mean_data(test_case,test_model_dict)
#    generate_mean_data(test_case,test_model_dict, function_list=mean_functions)
#    generate_sensitivity_data(test_case, test_model_dict, data_generator=tu.sum_infeas)

    ## Generate plots
    #---- Sensitivity plots: remove lazy and tolerance models
    for key, val in test_model_dict.items():
        if 'lazy' in key or '_e' in key:
            test_model_dict[key] = False
#    generate_sensitivity_plot(test_case, test_model_dict, plot_data='sum_infeas', units='p.u.', colors=colors, show_plot=show_plot)

    #---- Pareto plots: add lazy models
    for key, val in test_model_dict.items():
        if 'lazy' in key:
            test_model_dict[key] = True
#    generate_pareto_plot(test_case, test_model_dict, y_data='sum_infeas', x_data='solve_time', y_units='p.u', x_units='s',
#                         mark_default='o', mark_lazy='+', mark_acopf='*', mark_size=100, colors=colors,
#                         annotate_plot=False, show_plot=show_plot)

    #---- Case size plots:
    generate_case_size_plot(test_model_dict, case_list=case_names,
                            y_data='solve_time_geomean', y_units='s', x_data = 'num_buses', x_units=None,
                            s_data='num_constraints', colors=colors, show_plot=show_plot)

    #---- TODO: Factor truncation bar charts:

def idx_to_test_case(s):
    try:
        idx = int(s)
        tc = test_cases[idx]
        return tc
    except IndexError:
        raise SyntaxError("Index out of range of test_cases.")
    except ValueError:
        try:
            idx = case_names.index(s)
            tc = test_cases[idx]
            return tc
        except ValueError:
            raise SyntaxError(
                "Expecting argument of either A, B, C, D, E, or an index or case name from the test_cases list.")

if __name__ == '__main__':
    import sys

    if len(sys.argv[1:]) == 1:
        if sys.argv[1] == "A" or \
                sys.argv[1] == "B" or \
                sys.argv[1] == "C" or \
                sys.argv[1] == "D" or \
                sys.argv[1] == "E":
            main(sys.argv[1])
        else:
            submain(sys.argv[1])
    else:
        submain()

#    raise SyntaxError("Expecting a single string argument: test_cases0, test_cases1, test_cases2, test_cases3, or test_cases4")
