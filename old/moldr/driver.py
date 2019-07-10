""" drivers
"""
import functools
import numpy
from qcelemental import constants as qcc
import automol
import elstruct
import autofile
from autofile import SFS
from autofile import RFS
import moldr.runner


DEG2RAD = qcc.conversion_factor('degree', 'radian')
ANG2BOHR = qcc.conversion_factor('angstrom', 'bohr')


def run_conformers(ich, charge, mult, method, basis, orb_restricted,
                   nsamp, run_prefix, save_prefix, script_str, prog,
                   **kwargs):
    """ run sampling algorithm to find conformers
    """
    geo = automol.inchi.geometry(ich)
    zma = automol.geom.zmatrix(geo)
    tors_names = automol.geom.zmatrix_torsion_coordinate_names(geo)
    tors_range_vals = automol.zmatrix.torsional_sampling_ranges(
        zma, tors_names)
    tors_ranges = dict(zip(tors_names, tors_range_vals))

    if not tors_ranges:
        print("No torsional coordinates. Setting nsamp to 1.")
        nsamp = 1

    root_specs = (ich, charge, mult, method, basis, orb_restricted)

    # check for a previously saved run
    vma = automol.zmatrix.var_(zma)
    if SFS.conf_trunk.dir.exists(save_prefix, root_specs):
        _vma = SFS.conf_trunk.file.vmatrix.read(save_prefix, root_specs)
        assert vma == _vma
        inf_obj = SFS.conf_trunk.file.info.read(save_prefix, root_specs)
        nsamp = max(nsamp - inf_obj.nsamp, 0)
        print("Found previous saved run. Adjusting nsamp.")
        print("    New nsamp is {:d}.".format(nsamp))
    else:
        SFS.conf_trunk.dir.create(save_prefix, root_specs)
        inf_obj = autofile.system.info.conformer_trunk(
            nsamp=0, tors_ranges=tors_ranges)
    SFS.conf_trunk.file.vmatrix.write(vma, save_prefix, root_specs)
    SFS.conf_trunk.file.info.write(inf_obj, save_prefix, root_specs)

    # update the number of samples

    inp_zmas = automol.zmatrix.samples(zma, nsamp, tors_ranges)

    cids = tuple(autofile.system.generate_new_conformer_id()
                 for _ in range(nsamp))

    print()
    print("Running optimizations in run directories.")
    for idx, (cid, inp_zma) in enumerate(zip(cids, inp_zmas)):
        specs = root_specs + (cid,)

        if not SFS.conf.dir.exists(run_prefix, specs):
            SFS.conf.dir.create(run_prefix, specs)

        path = SFS.conf.dir.path(run_prefix, specs)

        print("Run {}/{}".format(idx+1, nsamp))
        run_job(
            job=elstruct.Job.OPTIMIZATION,
            script_str=script_str,
            prefix=path,
            geom=inp_zma,
            charge=charge,
            mult=mult,
            method=method,
            basis=basis,
            prog=prog,
            **kwargs
        )


def save_conformers(ich, charge, mult, method, basis, orb_restricted,
                    run_prefix, save_prefix):
    """ save the conformers that have been found so far
    """
    root_specs = (ich, charge, mult, method, basis, orb_restricted)
    print('save_conf_test', run_prefix, root_specs)
    if SFS.conf_trunk.dir.exists(run_prefix, root_specs):
        run_conf_specs_lst = SFS.conf.dir.existing(run_prefix, root_specs)
        saved_conf_specs_lst = SFS.conf.dir.existing(save_prefix, root_specs)

        conf_specs_lst = []
        ene_lst = []
        geo_lst = []
        inp_str_lst = []
        inf_obj_lst = []

        print()
        print("Reading optimizations from run directories.")
        print(root_specs)
        run_specs = ('optimization',)
        for conf_specs in run_conf_specs_lst:
            specs = root_specs + conf_specs + run_specs

            run_path = SFS.conf_run.dir.path(run_prefix, specs)
            print("Reading from run at {}".format(run_path))

            if SFS.conf_run.file.output.exists(run_prefix, specs):
                inf_obj = SFS.conf_run.file.info.read(run_prefix, specs)
                inp_str = SFS.conf_run.file.input.read(run_prefix, specs)
                out_str = SFS.conf_run.file.output.read(run_prefix, specs)
                prog = inf_obj.prog
                if elstruct.reader.has_normal_exit_message(prog, out_str):
                    ene = elstruct.reader.energy(prog, method, out_str)
                    geo = elstruct.reader.opt_geometry(prog, out_str)

                    # save the information to a list
                    conf_specs_lst.append(conf_specs)
                    inf_obj_lst.append(inf_obj)
                    inp_str_lst.append(inp_str)
                    ene_lst.append(ene)
                    geo_lst.append(geo)

        seen_geo_lst = []
        for conf_specs in saved_conf_specs_lst:
            specs = root_specs + conf_specs
            geo = SFS.conf.file.geometry.read(save_prefix, specs)
            seen_geo_lst.append(geo)

        print("Writing unique conformer information to save directories.")
        idxs = automol.geom.argunique_coulomb_spectrum(
            geo_lst, seen_geos=seen_geo_lst, rtol=1e-3)
        for idx in idxs:
            conf_specs = conf_specs_lst[idx]
            inf_obj = inf_obj_lst[idx]
            inp_str = inp_str_lst[idx]
            ene = ene_lst[idx]
            geo = geo_lst[idx]

            specs = root_specs + conf_specs
            save_path = SFS.conf.dir.path(save_prefix, specs)
            print("Saving values from run at {}".format(save_path))

            SFS.conf.dir.create(save_prefix, specs)
            SFS.conf.file.geometry_info.write(inf_obj, save_prefix, specs)
            SFS.conf.file.geometry_input.write(inp_str, save_prefix, specs)
            SFS.conf.file.energy.write(ene, save_prefix, specs)
            SFS.conf.file.geometry.write(geo, save_prefix, specs)

        # update the number of samples
        nsamp_new = len(conf_specs_lst)
        trunk_inf_obj = SFS.conf_trunk.file.info.read(save_prefix, root_specs)
        trunk_inf_obj.nsamp += nsamp_new
        SFS.conf_trunk.file.info.write(trunk_inf_obj, save_prefix, root_specs)

        # finally, update the conformer trajectory file
        conf_specs_lst = SFS.conf.dir.existing(save_prefix, root_specs)
        ene_lst = [
            SFS.conf.file.energy.read(save_prefix, root_specs+conf_specs)
            for conf_specs in conf_specs_lst]
        geo_lst = [
            SFS.conf.file.geometry.read(save_prefix, root_specs+conf_specs)
            for conf_specs in conf_specs_lst]

        traj = []
        for ene, geo in sorted(zip(ene_lst, geo_lst), key=lambda x: x[0]):
            comment = 'energy: {:>15.10f}'.format(ene)
            traj.append((comment, geo))

        SFS.conf_trunk.file.trajectory.write(traj, save_prefix, root_specs)


def run_conformer_job(ich, charge, mult, method, basis, orb_restricted, job,
                      run_prefix, save_prefix, script_str, prog,
                      **kwargs):
    """ run a job at each conformer point
    """
    root_specs = (ich, charge, mult, method, basis, orb_restricted)

    for conf_specs in SFS.conf.dir.existing(save_prefix, root_specs):
        specs = root_specs + conf_specs
        geo = SFS.conf.file.geometry.read(save_prefix, specs)
        path = SFS.conf.dir.path(run_prefix, specs)

        print('Running conformer {}'.format(job))
        run_job(
            job=job,
            script_str=script_str,
            prefix=path,
            geom=geo,
            charge=charge,
            mult=mult,
            method=method,
            basis=basis,
            prog=prog,
            **kwargs
        )


def run_scan(ich, charge, mult, method, basis, orb_restricted, cid,
             run_prefix, save_prefix, script_str, prog, scan_incr=30.,
             # ncoords,
             **kwargs):
    """ run a scan
    """
    root_specs = (ich, charge, mult, method, basis, orb_restricted, cid)
    if not SFS.conf.file.geometry.exists(save_prefix, root_specs):
        print('Conformer geometry file does not exist. Skipping ...')
    else:
        geo = SFS.conf.file.geometry.read(save_prefix, root_specs)
        zma = automol.geom.zmatrix(geo)

        vma = automol.zmatrix.var_(zma)
        if SFS.scan_trunk.dir.exists(save_prefix, root_specs):
            _vma = SFS.scan_trunk.file.vmatrix.read(save_prefix, root_specs)
            assert vma == _vma
        SFS.scan_trunk.dir.create(save_prefix, root_specs)
        SFS.scan_trunk.file.vmatrix.write(vma, save_prefix, root_specs)

        print(root_specs)
        print("Running hindered rotor scan for {:s}".format(cid))

        tors_names = automol.geom.zmatrix_torsion_coordinate_names(geo)
        increment = scan_incr * DEG2RAD
        tors_linspace_vals = automol.zmatrix.torsional_scan_grids(
            zma, tors_names, increment)
        tors_linspaces = dict(zip(tors_names, tors_linspace_vals))

        for tors_name, linspace in tors_linspaces.items():
            branch_specs = root_specs + ([tors_name],)
            inf_obj = autofile.system.info.scan_branch({tors_name: linspace})

            SFS.scan_branch.dir.create(save_prefix, branch_specs)
            SFS.scan_branch.file.info.write(inf_obj, save_prefix, branch_specs)

            last_zma = zma

            grid = numpy.linspace(*linspace)
            npoint = len(grid)
            for grid_idx, grid_val in enumerate(grid):
                specs = branch_specs + ((grid_idx,),)
                inp_zma = automol.zmatrix.set_values(
                    last_zma, {tors_name: grid_val})

                if not SFS.scan.dir.exists(run_prefix, specs):
                    SFS.scan.dir.create(run_prefix, specs)

                path = SFS.scan.dir.path(run_prefix, specs)

                print("Point {}/{}".format(grid_idx+1, npoint))
                run_job(
                    job=elstruct.Job.OPTIMIZATION,
                    script_str=script_str,
                    prefix=path,
                    geom=inp_zma,
                    charge=charge,
                    mult=mult,
                    method=method,
                    basis=basis,
                    prog=prog,
                    frozen_coordinates=[tors_name],
                    **kwargs
                )

                run_specs = specs + ('optimization',)
                if SFS.scan_run.file.output.exists(run_prefix, run_specs):
                    out_str = SFS.scan_run.file.output.read(run_prefix,
                                                            run_specs)
                    if elstruct.reader.has_normal_exit_message(prog, out_str):
                        last_zma = elstruct.reader.opt_zmatrix(prog, out_str)

            # now, run through in reverse to fill in the ones we missed
            grid = numpy.linspace(*linspace)
            npoint = len(grid)
            for grid_idx, grid_val in reversed(list(enumerate(grid))):
                specs = branch_specs + ((grid_idx,),)
                inp_zma = automol.zmatrix.set_values(
                    last_zma, {tors_name: grid_val})

                if not SFS.scan.dir.exists(run_prefix, specs):
                    SFS.scan.dir.create(run_prefix, specs)

                path = SFS.scan.dir.path(run_prefix, specs)

                print("Point {}/{}".format(grid_idx+1, npoint))
                run_job(
                    job=elstruct.Job.OPTIMIZATION,
                    script_str=script_str,
                    prefix=path,
                    geom=inp_zma,
                    charge=charge,
                    mult=mult,
                    method=method,
                    basis=basis,
                    prog=prog,
                    frozen_coordinates=[tors_name],
                    **kwargs
                )

                run_specs = specs + ('optimization',)
                if SFS.scan_run.file.output.exists(run_prefix, run_specs):
                    out_str = SFS.scan_run.file.output.read(run_prefix,
                                                            run_specs)
                    if elstruct.reader.has_normal_exit_message(prog, out_str):
                        last_zma = elstruct.reader.opt_zmatrix(prog, out_str)


def save_scan(ich, charge, mult, method, basis, orb_restricted, cid,
              run_prefix, save_prefix):
    """ save geometries and energies from a scan
    """
    root_specs = (ich, charge, mult, method, basis, orb_restricted, cid)
    for branch_specs in SFS.scan_branch.dir.existing(run_prefix, root_specs):

        print("Reading constrained optimizations from run directories.")
        for scan_specs in SFS.scan.dir.existing(
                run_prefix, root_specs+branch_specs):

            specs = root_specs + branch_specs + scan_specs

            run_specs = specs + ('optimization',)
            run_path = SFS.scan_run.dir.path(run_prefix, run_specs)
            print("Reading from scan run at {}".format(run_path))

            if SFS.scan_run.file.output.exists(run_prefix, run_specs):
                inf_obj = SFS.scan_run.file.info.read(run_prefix, run_specs)
                inp_str = SFS.scan_run.file.input.read(run_prefix, run_specs)
                out_str = SFS.scan_run.file.output.read(run_prefix, run_specs)
                prog = inf_obj.prog
                if not elstruct.reader.has_normal_exit_message(prog, out_str):
                    print("Job failed. Skipping ...")
                else:
                    ene = elstruct.reader.energy(prog, method, out_str)
                    geo = elstruct.reader.opt_geometry(prog, out_str)

                    save_path = SFS.scan.dir.path(save_prefix, specs)
                    print("Saving values from scan run at {}"
                          .format(save_path))

                    SFS.scan.dir.create(save_prefix, specs)
                    SFS.scan.file.geometry_info.write(
                        inf_obj, save_prefix, specs)
                    SFS.scan.file.geometry_input.write(
                        inp_str, save_prefix, specs)
                    SFS.scan.file.energy.write(ene, save_prefix, specs)
                    SFS.scan.file.geometry.write(geo, save_prefix, specs)

        # finally, update the scan trajectory file
        leaf_specs_lst = SFS.scan.dir.existing(
            save_prefix, root_specs+branch_specs)
        ene_lst = [
            SFS.scan.file.energy.read(
                save_prefix, root_specs+branch_specs+leaf_specs)
            for leaf_specs in leaf_specs_lst]
        geo_lst = [
            SFS.scan.file.geometry.read(
                save_prefix, root_specs+branch_specs+leaf_specs)
            for leaf_specs in leaf_specs_lst]

        traj = []
        for leaf_specs, ene, geo in sorted(
                zip(leaf_specs_lst, ene_lst, geo_lst), key=lambda x: x[0]):
            grid_idxs, = leaf_specs
            point_str = ', '.join(map('{:0>2d}'.format, grid_idxs))
            comment = 'point: {:s}; energy: {:>15.10f}'.format(
                point_str, ene)
            traj.append((comment, geo))

        SFS.scan_branch.file.trajectory.write(
            traj, save_prefix, root_specs+branch_specs)


def run_tau(ich, charge, mult, method, basis, orb_restricted,
            nsamp, run_prefix, save_prefix, script_str, prog,
            **kwargs):
    """ run sampling algorithm to find taus
    """
    geo = automol.inchi.geometry(ich)
    zma = automol.geom.zmatrix(geo)
    tors_names = automol.geom.zmatrix_torsion_coordinate_names(geo)
    tors_range_vals = automol.zmatrix.torsional_sampling_ranges(
        zma, tors_names)
    tors_ranges = dict(zip(tors_names, tors_range_vals))

    if not tors_ranges:
        print("No torsional coordinates. Setting nsamp to 1.")
        nsamp = 1

    root_specs = (ich, charge, mult, method, basis, orb_restricted)

    # check for a previously saved run
    vma = automol.zmatrix.var_(zma)
    if SFS.tau_trunk.dir.exists(save_prefix, root_specs):
        _vma = SFS.tau_trunk.file.vmatrix.read(save_prefix, root_specs)
        assert vma == _vma
        inf_obj = SFS.tau_trunk.file.info.read(save_prefix, root_specs)
        nsamp = max(nsamp - inf_obj.nsamp, 0)
        print("Found previous saved run. Adjusting nsamp.")
        print("    New nsamp is {:d}.".format(nsamp))
    else:
        SFS.tau_trunk.dir.create(save_prefix, root_specs)
        inf_obj = autofile.system.info.tau_trunk(
            nsamp=0, tors_ranges=tors_ranges)
    SFS.tau_trunk.file.vmatrix.write(vma, save_prefix, root_specs)
    SFS.tau_trunk.file.info.write(inf_obj, save_prefix, root_specs)

    # update the number of samples

    inp_zmas = automol.zmatrix.samples(zma, nsamp, tors_ranges)

    cids = tuple(autofile.system.generate_new_conformer_id()
                 for _ in range(nsamp))

    print()
    print("Running tau optimizations in run directories.")
    for idx, (cid, inp_zma) in enumerate(zip(cids, inp_zmas)):
        specs = root_specs + (cid,)

        if not SFS.tau.dir.exists(run_prefix, specs):
            SFS.tau.dir.create(run_prefix, specs)

        path = SFS.tau.dir.path(run_prefix, specs)

        print("Run {}/{}".format(idx+1, nsamp))
        run_job(
            job=elstruct.Job.OPTIMIZATION,
            script_str=script_str,
            prefix=path,
            geom=inp_zma,
            charge=charge,
            mult=mult,
            method=method,
            basis=basis,
            prog=prog,
            frozen_coordinates=tors_names,
            **kwargs
        )


def save_tau(ich, charge, mult, method, basis, orb_restricted,
             run_prefix, save_prefix):
    """ save the taus that have been found so far
    """
    root_specs = (ich, charge, mult, method, basis, orb_restricted)
    run_tau_specs_lst = SFS.tau.dir.existing(run_prefix, root_specs)

    tau_specs_lst = []

    print()
    print("Reading optimizations from run directories.")
    run_specs = ('optimization',)
    for tau_specs in run_tau_specs_lst:
        specs = root_specs + tau_specs + run_specs

        run_path = SFS.tau_run.dir.path(run_prefix, specs)
        print("Reading from run at {}".format(run_path))

        if SFS.tau_run.file.output.exists(run_prefix, specs):
            inf_obj = SFS.tau_run.file.info.read(run_prefix, specs)
            inp_str = SFS.tau_run.file.input.read(run_prefix, specs)
            out_str = SFS.tau_run.file.output.read(run_prefix, specs)
            prog = inf_obj.prog
            if elstruct.reader.has_normal_exit_message(prog, out_str):
                ene = elstruct.reader.energy(prog, method, out_str)
                geo = elstruct.reader.opt_geometry(prog, out_str)

            print(automol.geom.coulomb_spectrum(geo))
            save_specs = root_specs + tau_specs
            save_path = SFS.tau.dir.path(save_prefix, save_specs)
            print("Saving values from run at {}".format(save_path))

            SFS.tau.dir.create(save_prefix, save_specs)
            SFS.tau.file.geometry_info.write(inf_obj, save_prefix, save_specs)
            SFS.tau.file.geometry_input.write(inp_str, save_prefix, save_specs)
            SFS.tau.file.energy.write(ene, save_prefix, save_specs)
            SFS.tau.file.geometry.write(geo, save_prefix, save_specs)

    # update the number of samples
    nsamp_new = len(tau_specs_lst)
    trunk_inf_obj = SFS.tau_trunk.file.info.read(save_prefix, root_specs)
    trunk_inf_obj.nsamp += nsamp_new
    SFS.tau_trunk.file.info.write(trunk_inf_obj, save_prefix, root_specs)


def run_tau_job(ich, charge, mult, method, basis, orb_restricted, job,
                run_prefix, save_prefix, script_str, prog, vignore=1e10,
                **kwargs):
    """ run gradients or hessians for taus
    """
    root_specs = (ich, charge, mult, method, basis, orb_restricted)

    print()
    print("Reading optimizations from run directories as prelude to hessians.")

    for tau_specs in SFS.tau.dir.existing(save_prefix, root_specs):
        specs = root_specs + tau_specs
        geo = SFS.tau.file.geometry.read(save_prefix, specs)
        ene = SFS.tau.file.energy.read(save_prefix, specs)
        if ene < vignore:
            path = SFS.tau.dir.path(run_prefix, specs)

            print("Running tau {}".format(job))
            run_job(
                job=job,
                script_str=script_str,
                prefix=path,
                geom=geo,
                charge=charge,
                mult=mult,
                method=method,
                basis=basis,
                prog=prog,
                **kwargs
            )


# gridopt functions
def run_gridopt(rxn_inchis, rxn_charges, rxn_mults, method, basis,
                orb_restricted, ts_mult, run_prefix, save_prefix, script_str,
                prog,
                dist_start=1.0*ANG2BOHR,
                dist_increment=0.1*ANG2BOHR,
                npoints=15,
                **kwargs):
    """ grid optimization for transition state guess
    """

    assert save_prefix is not None  # do-nothing line for style checkers
    print("The transition state multiplicity is", ts_mult)

    reactant_inchis = rxn_inchis[0]
    product_inchis = rxn_inchis[1]

    reactant_geoms = list(map(automol.inchi.geometry, reactant_inchis))
    product_geoms = list(map(automol.inchi.geometry, product_inchis))

    reactant_zmats = list(map(automol.geom.zmatrix, reactant_geoms))
    product_zmats = list(map(automol.geom.zmatrix, product_geoms))

    ret = automol.zmatrix.ts.beta_scission(reactant_zmats,
                                           product_zmats)
    if ret is None:
        ret = automol.zmatrix.ts.addition(reactant_zmats,
                                          product_zmats)
    if ret is None:
        ret = automol.zmatrix.ts.hydrogen_abstraction(reactant_zmats,
                                                      product_zmats)
    if ret is None:
        print("Failed to identify reaction type")

    # get stereo-specific inchis from the geometries
    reactant_inchis = list(map(automol.inchi.standard_form,
                               map(automol.geom.inchi, reactant_geoms)))
    product_inchis = list(map(automol.inchi.standard_form,
                              map(automol.geom.inchi, product_geoms)))
    rxn_inchis = (reactant_inchis, product_inchis)
    root_specs = (rxn_inchis, rxn_charges, rxn_mults, ts_mult, method, basis,
                  orb_restricted)

    if ret is None:
        print("Failed to classify reaction for this system.")
    else:
        ts_zmat, dist_name = ret
        grid_zmats = [
            automol.zmatrix.set_values(
                ts_zmat, {dist_name: dist_start + dist_increment * num})
            for num in range(npoints)]

        for grid_index, grid_zmat in enumerate(grid_zmats):
            specs = root_specs + ((dist_name,), (grid_index,))
            path = RFS.scan.dir.path(run_prefix, specs)

            if not RFS.scan.dir.exists(run_prefix, specs):
                RFS.scan.dir.create(run_prefix, specs)

            print("Point {}/{}".format(grid_index+1, npoints))
            run_job(
                job=elstruct.Job.OPTIMIZATION,
                script_str=script_str,
                prefix=path,
                geom=grid_zmat,
                charge=sum(rxn_charges[0]),
                mult=ts_mult,
                method=method,
                basis=basis,
                prog=prog,
                frozen_coordinates=[dist_name],
                **kwargs
            )


def save_gridopt(rxn_inchis, rxn_charges, rxn_mults, method, basis,
                 orb_restricted, ts_mult, run_prefix, save_prefix):
    """ save grid optimization results

    (ultimately, we don't actually care about this information, but we want it
    for debugging purposes)
    """
    root_specs = (rxn_inchis, rxn_charges, rxn_mults, ts_mult, method, basis,
                  orb_restricted)
    branch_specs = RFS.scan_branch.dir.existing(run_prefix, root_specs)
    if branch_specs:
        assert len(branch_specs) == 1
        root_specs += branch_specs[0]

        for scan_specs in RFS.scan.dir.existing(run_prefix, root_specs):
            specs = root_specs + scan_specs

            print("Reading grid points from run directories.")
            run_specs = specs + ('optimization',)
            run_path = RFS.scan_run.dir.path(run_prefix, run_specs)
            print("Reading from gridopt run at {}".format(run_path))

            if RFS.scan_run.file.output.exists(run_prefix, run_specs):
                inf_obj = RFS.scan_run.file.info.read(run_prefix, run_specs)
                inp_str = RFS.scan_run.file.input.read(run_prefix, run_specs)
                out_str = RFS.scan_run.file.output.read(run_prefix, run_specs)
                prog = inf_obj.prog
                if not elstruct.reader.has_normal_exit_message(prog, out_str):
                    print("Job failed. Skipping ...")
                else:
                    ene = elstruct.reader.energy(prog, method, out_str)
                    geo = elstruct.reader.opt_geometry(prog, out_str)

                    save_path = RFS.scan.dir.path(save_prefix, specs)
                    print("Saving values from scan run at {}"
                          .format(save_path))

                    RFS.scan.dir.create(save_prefix, specs)
                    RFS.scan.file.geometry_info.write(
                        inf_obj, save_prefix, specs)
                    RFS.scan.file.geometry_input.write(
                        inp_str, save_prefix, specs)
                    RFS.scan.file.energy.write(ene, save_prefix, specs)
                    RFS.scan.file.geometry.write(geo, save_prefix, specs)

        # finally, update the scan trajectory file
        leaf_specs_lst = RFS.scan.dir.existing(save_prefix, root_specs)
        ene_lst = [
            RFS.scan.file.energy.read(save_prefix, root_specs+leaf_specs)
            for leaf_specs in leaf_specs_lst]
        geo_lst = [
            RFS.scan.file.geometry.read(save_prefix, root_specs+leaf_specs)
            for leaf_specs in leaf_specs_lst]

        traj = []
        for leaf_specs, ene, geo in sorted(
                zip(leaf_specs_lst, ene_lst, geo_lst), key=lambda x: x[0]):
            grid_idxs, = leaf_specs
            point_str = ', '.join(map('{:0>2d}'.format, grid_idxs))
            comment = 'point: {:s}; energy: {:>15.10f}'.format(
                point_str, ene)
            traj.append((comment, geo))

        RFS.scan_branch.file.trajectory.write(traj, save_prefix, root_specs)


# centralized job runner
def run_job(job, script_str, prefix,
            geom, charge, mult, method, basis, prog,
            errors=(), options_mat=(), retry_failed=True,
            **kwargs):
    """ run an elstruct job by name
    """
    runner_dct = {
        elstruct.Job.ENERGY: functools.partial(
            moldr.runner.options_matrix_run, elstruct.writer.energy),
        elstruct.Job.GRADIENT: functools.partial(
            moldr.runner.options_matrix_run, elstruct.writer.gradient),
        elstruct.Job.HESSIAN: functools.partial(
            moldr.runner.options_matrix_run, elstruct.writer.hessian),
        elstruct.Job.OPTIMIZATION: moldr.runner.feedback_optimization,
    }

    assert job in runner_dct

    run_trunk_ds = autofile.system.series.run_trunk()
    run_ds = autofile.system.series.run_leaf(root_dsdir=run_trunk_ds.dir)

    run_path = run_ds.dir.path(prefix, [job])
    if not run_ds.file.info.exists(prefix, [job]):
        do_run = True
        print(" - Running {} job at {}".format(job, run_path))
    else:  
        inf_obj = run_ds.file.info.read(prefix, [job])
        if inf_obj.status == autofile.system.RunStatus.FAILURE:
            print(" - Found failed {} job at {}".format(job, run_path))
            if retry_failed:
                print(" - Retrying...")
                do_run = True
            else:
                do_run = False
        else:
            do_run = False
            if inf_obj.status == autofile.system.RunStatus.SUCCESS:
                print(" - Found completed {} job at {}".format(job, run_path))
            else:
                print(" - Found running {} job at {}".format(job, run_path))
            print(" - Skipping...")

    if do_run:
        # create the run directory
        run_ds.dir.create(prefix, [job])

        run_path = run_ds.dir.path(prefix, [job])

        status = autofile.system.RunStatus.RUNNING
        inf_obj = autofile.system.info.run(
            job=job, prog=prog, method=method, basis=basis, status=status)
        inf_obj.utc_start_time = autofile.system.info.utc_time()
        run_ds.file.info.write(inf_obj, prefix, [job])

        runner = runner_dct[job]

        print(" - Starting the run...")
        inp_str, out_str = runner(
            script_str, run_path,
            geom=geom, charge=charge, mult=mult, method=method,
            basis=basis, prog=prog, errors=errors, options_mat=options_mat,
            **kwargs
        )

        inf_obj.utc_end_time = autofile.system.info.utc_time()

        if elstruct.reader.has_normal_exit_message(prog, out_str):
            run_ds.file.output.write(out_str, prefix, [job])
            print(" - Run succeeded.")
            status = autofile.system.RunStatus.SUCCESS
        else:
            print(" - Run failed.")
            status = autofile.system.RunStatus.FAILURE
        inf_obj.status = status
        run_ds.file.info.write(inf_obj, prefix, [job])
        run_ds.file.input.write(inp_str, prefix, [job])