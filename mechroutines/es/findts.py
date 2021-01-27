"""
  TS Finding algorithms
"""

import automol
import autofile
from mechroutines.es._routines import _sadpt as sadpt
from mechroutines.es._routines import _vrctst as vrctst
from mechroutines.es._routines import _vtst as vtst
from mechroutines.es._routines import _wfn as wfn
from mechlib import filesys
from mechlib.submission import qchem_params
from mechlib.amech_io import printer as ioprinter


def run(job, spc_dct, spc_name, thy_dct, es_keyword_dct,
        run_prefix, save_prefix):
    """ find a transition state
    """
    var_sp1_thy_info, var_sp2_thy_info, var_scn_thy_info = None, None, None

    # Get dct for specific species task is run for
    ts_dct = spc_dct[spc_name]

    # Build inf objects for the rxn and ts
    ts_info = ('', spc_dct[spc_name]['charge'], spc_dct[spc_name]['mult'])
    rxn_info = filesys.inf.rxn_info(
        spc_dct[spc_name]['reacs'], spc_dct[spc_name]['prods'], spc_dct)

    # Set various TS information using the dictionary
    ini_zma = ts_dct['zma']
    typ = ts_dct['class']

    dist_info = ts_dct['dist_info']
    dist_name, _, update_guess, brk_name, _ = dist_info
    frm_bnd_keys = ts_dct['frm_bnd_keys']
    brk_bnd_keys = ts_dct['brk_bnd_keys']
    rcts_gra = ts_dct['rcts_gra']
    const_bnd_key = ts_dct['const_bnd_key']
    const_tors_names = ts_dct['const_tors_names']
    const_angs_names = ts_dct['const_angs_names']
    constraint_dct = {}
    if const_bnd_key:
        const_name = automol.zmat.bond_key_from_idxs(
            ini_zma, const_bnd_key)
        coords = automol.zmat.value_dictionary(ini_zma)
        const_val = coords[const_name]
        constraint_dct[const_name] = const_val
    if const_tors_names:
        coords = automol.zmat.value_dictionary(ini_zma)
        for const_tors_name in const_tors_names:
            const_val = coords[const_tors_name]
            constraint_dct[const_tors_name] = const_val
    if const_angs_names:
        coords = automol.zmat.value_dictionary(ini_zma)
        for const_angs_name in const_angs_names:
            const_val = coords[const_angs_name]
            constraint_dct[const_angs_name] = const_val
    if not constraint_dct:
        constraint_dct = None
    ioprinter.constraint_dictionary(constraint_dct)

    # set ts searching algorithm and grid info
    typ = ts_dct['class']
    if 'ts_search' in ts_dct:
        ts_search = ts_dct['ts_search']
        usr_choice = True
    elif 'ts_search' not in ts_dct and 'rad' in typ and 'low' in typ:
        ts_search = 'vtst'
        usr_choice = False
    else:
        ts_search = 'sadpt'
        usr_choice = False
    # elif 'ts_search' not in ts_dct and 'rad' not in typ:

    if ts_search in ('vtst', 'vrctst'):
        if 'rad' in typ:
            grid = ts_dct['grid']
        else:
            grid = ts_dct['var_grid']
    else:
        grid = ts_dct['grid']

    # Get es options
    vrc_dct = {}
    overwrite = es_keyword_dct['overwrite']
    nobar_mod = es_keyword_dct['nobarrier']

    # Modify the theory
    ini_thy_info = filesys.inf.get_es_info(
        es_keyword_dct['inplvl'], thy_dct)
    thy_info = filesys.inf.get_es_info(
        es_keyword_dct['runlvl'], thy_dct)
    mod_thy_info = filesys.inf.modify_orb_restrict(ts_info, thy_info)
    mod_ini_thy_info = filesys.inf.modify_orb_restrict(ts_info, ini_thy_info)

    # Build filesys for thy info for single reference
    _, thy_run_path = filesys.build.rxn_thy_fs_from_root(
        run_prefix, rxn_info, mod_thy_info)
    thy_save_fs, thy_save_path = filesys.build.rxn_thy_fs_from_root(
        save_prefix, rxn_info, mod_thy_info)

    # Build filesys for ini thy info for single reference
    _, ini_thy_save_path = filesys.build.rxn_thy_fs_from_root(
        save_prefix, rxn_info, mod_ini_thy_info)

    # Build the ts fs
    ts_save_fs, ts_save_path = filesys.build.ts_fs_from_thy(thy_save_path)
    _, ts_run_path = filesys.build.ts_fs_from_thy(thy_run_path)
    run_fs = autofile.fs.run(ts_run_path)

    # Build the ts fs (only need save to see if guess zmat can be found)
    _, ini_ts_save_path = filesys.build.ts_fs_from_thy(
        ini_thy_save_path)

    # Set the cnf fs to see if TS is available or for searching
    cnf_save_fs = autofile.fs.conformer(ts_save_path)
    min_cnf_locs, _ = filesys.mincnf.min_energy_conformer_locators(
        cnf_save_fs, mod_thy_info)

    # Find the transition state using the appropriate algorithm
    switch = False
    _print_ts_method(
        ts_dct, ts_search, usr_choice, es_keyword_dct['nobarrier'])

    # Run multireference VTST or VRCTST TS Search
    if _radrad_barrierless_search(ts_dct, ts_search):

        ioprinter.info_message('VRCTST/VTST')

        # Modify the theory
        hs_info = (ts_info[0], ts_info[1], ts_dct['high_mult'])
        mod_var_scn_thy_info = filesys.inf.modify_orb_restrict(
            ts_info, var_scn_thy_info)
        hs_var_scn_thy_info = filesys.inf.modify_orb_restrict(
            hs_info, var_scn_thy_info)
        mod_var_sp1_thy_info = filesys.inf.modify_orb_restrict(
            ts_info, var_sp1_thy_info)
        hs_var_sp1_thy_info = filesys.inf.modify_orb_restrict(
            hs_info, var_sp1_thy_info)
        if var_sp2_thy_info is not None:
            mod_var_sp2_thy_info = filesys.inf.modify_orb_restrict(
                ts_info, var_sp2_thy_info)
            hs_var_sp2_thy_info = filesys.inf.modify_orb_restrict(
                hs_info, var_sp2_thy_info)
        else:
            mod_var_sp2_thy_info = None
            hs_var_sp2_thy_info = None

        # Build multireference thy info objects
        if mod_var_scn_thy_info:
            _, thy_run_path = filesys.build.rxn_thy_fs_from_root(
                run_prefix, rxn_info, mod_var_scn_thy_info)
            _, thy_save_path = filesys.build.rxn_thy_fs_from_root(
                save_prefix, rxn_info, mod_var_scn_thy_info)
            scn_run_fs = autofile.fs.scan(thy_run_path)
            scn_save_fs = autofile.fs.scan(thy_save_path)
        else:
            ioprinter.missing_input('mlvl')
        if mod_var_sp1_thy_info:
            _, thy_run_path = filesys.build.rxn_thy_fs_from_root(
                run_prefix, rxn_info, mod_var_sp1_thy_info)
            _, thy_save_path = filesys.build.rxn_thy_fs_from_root(
                save_prefix, rxn_info, mod_var_sp1_thy_info)
        else:
            ioprinter.missing_input('mlvl')
        if mod_var_sp2_thy_info:
            _, thy_run_path = filesys.build.rxn_thy_fs_from_root(
                run_prefix, rxn_info, mod_var_sp2_thy_info)
            _, thy_save_path = filesys.build.rxn_thy_fs_from_root(
                save_prefix, rxn_info, mod_var_sp2_thy_info)
        else:
            ioprinter.missing_input('mlvl')

        # Set up the scan filesys (need scan and cscan for rc
        scn_run_fs = autofile.fs.scan(thy_run_path)
        scn_save_fs = autofile.fs.scan(thy_save_path)

        # Run the barrierless transition state
        barrierless_transition_state(
            ts_info, ini_zma, ts_dct, spc_dct,
            grid, dist_name,
            nobar_mod,
            mod_ini_thy_info, mod_thy_info,
            mod_var_scn_thy_info,
            mod_var_sp1_thy_info, mod_var_sp2_thy_info,
            hs_var_scn_thy_info,
            hs_var_sp1_thy_info,
            hs_var_sp2_thy_info,
            run_prefix, save_prefix,
            scn_run_fs, scn_save_fs,
            overwrite, vrc_dct,
            update_guess)

        # Print switch message
        if switch:
            ioprinter.info_message(
                'Analysis of computed surface suggests saddle point.')
            ioprinter.info_message(
                'Attempting to find saddle point using surface...')

    ioprinter.debug_message('ts_dct_grid test:', ts_dct['grid'])
    # Run single reference mol-rad VTST Search
    if _molrad_barrierless_search(ts_dct, ts_search):
        rcts = ts_dct['reacs']
        spc_1_info = [spc_dct[rcts[0]]['inchi'],
                      spc_dct[rcts[0]]['charge'],
                      spc_dct[rcts[0]]['mult']]
        spc_2_info = [spc_dct[rcts[1]]['inchi'],
                      spc_dct[rcts[1]]['charge'],
                      spc_dct[rcts[1]]['mult']]
        [grid1, grid2] = grid
        ioprinter.debug_message('in barrierless search', grid1, grid2, grid)
        # Set up the scan filesys (need scan and cscan for rc
        scn_run_fs = autofile.fs.scan(thy_run_path)
        scn_save_fs = autofile.fs.scan(thy_save_path)
        vtst.molrad_scan(
            ini_zma, ts_info,
            spc_1_info, spc_2_info,
            grid1, grid2, dist_name,
            thy_info, ini_thy_info,
            var_sp1_thy_info,
            scn_run_fs, scn_save_fs,
            run_prefix, save_prefix,
            overwrite, update_guess)

    # Run single/multi reference mol-rad Saddle Point Search
    if _sadpt_search(ts_dct, ts_search, switch):

        # ts_found = False
        if min_cnf_locs and not overwrite:

            ioprinter.existing_path(
                'TS', cnf_save_fs[-1].path(min_cnf_locs))
        else:

            ioprinter.info_message(
                'No transition state found in filesys',
                'at {} level...'.format(es_keyword_dct['runlvl']),
                'Proceeding to find it...')
            script_str, opt_script_str, _, opt_kwargs = qchem_params(
                *mod_thy_info[0:2])
            sadpt_transition_state(
                ini_zma, ts_info,
                mod_ini_thy_info, mod_thy_info,
                thy_run_path, thy_save_path,
                thy_save_fs,
                ini_ts_save_path,
                cnf_save_fs,
                ts_save_fs, ts_save_path, run_fs,
                typ, grid, update_guess,
                dist_name, brk_name,
                frm_bnd_keys, brk_bnd_keys, rcts_gra,
                opt_script_str, script_str, overwrite,
                es_keyword_dct, constraint_dct, **opt_kwargs)

    # if not ts_found:
    #    print('No TS was found...')


# SADPT FINDER FUNCTIONS
def sadpt_transition_state(
        ini_zma, ts_info,
        mod_ini_thy_info, mod_thy_info,
        thy_run_path, thy_save_path,
        thy_save_fs,
        ini_ts_save_path,
        cnf_save_fs,
        ts_save_fs, ts_save_path, run_fs,
        typ, grid, update_guess,
        dist_name, brk_name,
        frm_bnd_keys, brk_bnd_keys, rcts_gra,
        opt_script_str, script_str, overwrite,
        es_keyword_dct, constraint_dct, **opt_kwargs):
    """ Find a sadddle point
    """

    # Check filesystem for input level of theory
    ioprinter.info_message(
        'Searching save filesys for guess Z-Matrix calculated',
        'at {} level...'.format(es_keyword_dct['inplvl']), newline=1)
    guess_zmas = sadpt.check_filesys_for_guess(
        ini_ts_save_path, mod_ini_thy_info)

    # If no guess zma, run a TS searching algorithm
    if not guess_zmas:

        ioprinter.info_message(' - No Z-Matrix is found in save filesys.')
        ioprinter.mepssage(
            'Running scan to generate guess Z-Matrix for opt...', newline=1)
        # Set up ini filesystem for scans
        _, zma_run_path = filesys.build.zma_fs_from_prefix(
            thy_run_path, zma_idxs=[0])
        _, zma_save_path = filesys.build.zma_fs_from_prefix(
            thy_save_path, zma_idxs=[0])
        scn_run_fs = filesys.build.scn_fs_from_cnf(
            zma_run_path, constraint_dct=constraint_dct)
        scn_save_fs = filesys.build.scn_fs_from_cnf(
            zma_save_path, constraint_dct=constraint_dct)

        guess_zmas = sadpt.scan_for_guess(
            typ, grid, dist_name, brk_name, ini_zma, ts_info,
            mod_thy_info, thy_save_fs,
            scn_run_fs, scn_save_fs, opt_script_str,
            overwrite, update_guess, constraint_dct, **opt_kwargs)

    # Optimize the saddle point
    ioprinter.info_message(
        'Optimizing guess Z-Matrix obtained from scan or filesys...',
        newline=1)
    opt_ret = sadpt.optimize_saddle_point(
        guess_zmas, ts_info, mod_thy_info,
        run_fs, opt_script_str, overwrite, **opt_kwargs)

    # Calculate the Hessian for the optimized structure
    if opt_ret is not None:
        ioprinter.info_message(
            'Calculating Hessian for the optimized geometry...', newline=1)
        hess_ret, freqs, imags = sadpt.saddle_point_hessian(
            opt_ret, ts_info, mod_thy_info,
            run_fs, script_str, overwrite, **opt_kwargs)

        # Assess saddle point, save it if viable
        ioprinter.info_message('Assessing the saddle point...')
        saddle = sadpt.saddle_point_checker(imags)
        if saddle:
            sadpt.save_saddle_point(
                opt_ret, hess_ret, freqs, imags,
                mod_thy_info,
                cnf_save_fs,
                ts_save_fs, ts_save_path,
                frm_bnd_keys, brk_bnd_keys, rcts_gra,
                zma_locs=[0])
    else:
        ioprinter.warning_message(
            'TS optimization failed. No geom to check and save.', newline=1)


# Barrierless finder functions
def barrierless_transition_state(
        ts_info, ts_zma, ts_dct, spc_dct,
        grid,
        dist_name,
        rad_rad_ts,
        mod_ini_thy_info, mod_thy_info,
        mod_var_scn_thy_info,
        mod_var_sp1_thy_info, mod_var_sp2_thy_info,
        hs_var_scn_thy_info,
        hs_var_sp1_thy_info,
        hs_var_sp2_thy_info,
        run_prefix, save_prefix,
        scn_run_fs, scn_save_fs,
        overwrite, vrc_dct,
        update_guess, **opt_kwargs):
    """ Run TS finder for barrierless reactions
    """
    switch = False
    _ = vrc_dct

    # Set information from the transition state
    ts_formula = automol.geom.formula(automol.zmat.geometry(ts_zma))
    [grid1, grid2] = grid

    # Get info from the reactants
    # rct_zmas = ts_dct['rct_zmas']
    rcts = ts_dct['reacs']
    high_mul = ts_dct['high_mult']
    spc_1_info = [spc_dct[rcts[0]]['inchi'],
                  spc_dct[rcts[0]]['charge'],
                  spc_dct[rcts[0]]['mult']]
    spc_2_info = [spc_dct[rcts[1]]['inchi'],
                  spc_dct[rcts[1]]['charge'],
                  spc_dct[rcts[1]]['mult']]

    # Set the active space
    num_act_orb, num_act_elc = wfn.active_space(
        ts_dct, spc_dct, ts_dct['high_mult'])

    # Run PST, VTST, VRC-TST based on RAD_RAD_TS model
    if rad_rad_ts.lower() == 'pst':
        ts_found = True
        ioprinter.info_message('Phase Space Theory Used, No ES calculations are needed')
    elif rad_rad_ts.lower() == 'vtst':
        ts_found = True
        ioprinter.info_message('Beginning Calculations for VTST Treatments')
        vtst.radrad_scan(
            ts_zma, ts_info, ts_formula, high_mul,
            spc_1_info, spc_2_info,
            grid1, grid2, dist_name,
            num_act_orb, num_act_elc,
            mod_var_scn_thy_info,
            mod_var_sp1_thy_info, mod_var_sp2_thy_info,
            hs_var_scn_thy_info,
            hs_var_sp1_thy_info,
            hs_var_sp2_thy_info,
            mod_ini_thy_info, mod_thy_info,
            scn_run_fs, scn_save_fs,
            run_prefix, save_prefix,
            overwrite, update_guess,
            **opt_kwargs)
        # if ts_found:
        #     print('Scans for VTST succeeded')
        # else:
        #     print('Scans for VTST failed')
    elif rad_rad_ts.lower() == 'vrctst':
        # multi_level, multilevel is bad for some reason
        ioprinter.info_message('Beginning Calculations for VRC-TST Treatments')
        ts_found = vrctst.calc_vrctst_flux(
            ts_zma, ts_formula, ts_info, ts_dct, spc_dct,
            ts_dct['high_mult'], grid1, grid2, dist_name,
            mod_var_scn_thy_info,
            mod_var_scn_thy_info,
            mod_var_sp1_thy_info,
            mod_ini_thy_info, mod_thy_info,
            thy_run_path, thy_save_path,
            overwrite, update_guess,
            run_prefix, save_prefix,
            vrc_dct,
            corr_pot=True)
    #     if ts_found:
    #         print('VaReCoF run successful and flux file was obtained')
    #     else:
    #         print('VaReCoF run failed')

    return ts_found, switch


# Functions to check what TS searching algorithm to launch
def _radrad_barrierless_search(ts_dct, ts_search):
    """ Determine if we should search for rad-rad barrierless TS """
    ioprinter.debug_message('nobar', _nobarrier(ts_dct))
    return bool(
        _nobarrier(ts_dct) and ts_search in ('vtst', 'vrctst'))


def _molrad_barrierless_search(ts_dct, ts_search):
    """ Determine if we should search for mol-rad barrierless TS """
    return bool(
        not _nobarrier(ts_dct) and ts_search in ('vtst'))


def _sadpt_search(ts_dct, ts_search, switch):
    """ Determine if we should search for mol-rad saddle point TS """
    # Check if we are just looking for a sadpt on PES
    mol_or_molrad_sadpt = bool(
        not _nobarrier(ts_dct) and ts_search == 'sadpt')
    # Check if we are switching from a barrierless vtst, vrctst calc
    radrad_switch = bool(
        _nobarrier(ts_dct) and switch)
    return mol_or_molrad_sadpt or radrad_switch


def _nobarrier(ts_dct):
    """ Determine if reaction is barrierless
    """
    ioprinter.debug_message('cla', ts_dct['class'])
    rad_rad = bool('radical radical' in ts_dct['class'])
    low_spin = bool('low' in ts_dct['class'])
    return rad_rad and low_spin


def _print_ts_method(ts_dct, ts_search, usr_choice, nobarrier_mod):
    """ Print a message
    """
    # Print message about reaction type
    if _nobarrier(ts_dct):
        ioprinter.info_message(
            'Reaction is low-spin, radical-radical addition or abstraction')
    else:
        ioprinter.info_message(
            'Reaction is either (1) unimolecular, (2) molecule-radical, or',
            '(3) high-spin, radical-radical addition or abstraction')

    # Print message about request or assumed search algorithm
    if usr_choice:
        ioprinter.info_message(
            'Running search algorithm according to {},'.format(ts_search),
            'as requested by the user')
    else:
        if _nobarrier(ts_dct):
            ioprinter.info_message('Assuming reaction is barrierless...')
            ioprinter.info_message(
                'Finding a transition state according to the requested',
                '{} model...'.format(nobarrier_mod.upper()))
        else:
            ioprinter.info_message(
                'Assuming reaction has saddle point on potential surface...')
            ioprinter.info_message(
                'Finding the geometry of the saddle point...')
