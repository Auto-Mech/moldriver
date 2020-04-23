""" Handle symmetry factor stuff
"""

import automol
from routines.es import conformer


def symmetry_factor(sym_model, spc_dct_i, spc_info, dist_names,
                    saddle, frm_bnd_key, brk_bnd_key, tors_names,
                    cnf_save_fs, cnf_save_locs):
    """ Get the overall factor for a species
    """

    form_coords = []
    if 'sym' in spc_dct_i:
        sym_factor = spc_dct_i['sym']
        print('sym_factor from spc_dct_i:', sym_factor)
    else:
        if sym_model == 'sampling':
            if not cnf_save_locs:
                # Fix the return statement here
                print('ERROR: Reference geometry is missing for symmetry',
                      'for species {}'.format(spc_info[0]))
                return '', 0.
            sym_geo = cnf_save_fs[-1].file.geometry.read(cnf_save_locs)
            sym_ene = cnf_save_fs[-1].file.energy.read(cnf_save_locs)
            if dist_names:
                zma = cnf_save_fs[-1].file.zmatrix.read(cnf_save_locs)
                form_coords = list(
                    automol.zmatrix.bond_idxs(zma, dist_names[0]))
                form_coords.extend(list(dist_names[1]))
            sym_factor = conformer.symmetry_factor(
                sym_geo, sym_ene, cnf_save_fs, saddle,
                frm_bnd_key, brk_bnd_key, form_coords, tors_names)
            print('sym_factor from conformer sampling:', sym_factor)
        elif sym_model == '1dhr':
            print('Warning: the 1DHR based symmetry number',
                  'has not yet been implemented, setting symf to 1.0')
            sym_factor = 1.0
        else:
            # print('Warning: no symmetry model requested,',
            #       'setting symmetry factor to 1.0')
            sym_factor = 1.0

    return sym_factor


def tors_reduced_sym_factor(sym_factor, tors_syms):
    """ Decrease the overall molecular symmetry factor by the
        torsional mode symmetry numbers
    """
    for sym_num in tors_syms:
        sym_factor /= sym_num

    return sym_factor