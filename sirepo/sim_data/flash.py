# -*- coding: utf-8 -*-
u"""simulation data operations

:copyright: Copyright (c) 2019 RadiaSoft LLC.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""
from __future__ import absolute_import, division, print_function
import sirepo.sim_data
import sirepo.util



class SimData(sirepo.sim_data.SimDataBase):

    EXE_NAME = 'flash4'
    SETUP_UNITS_FILE = 'setup_units'

    @classmethod
    def fixup_old_data(cls, data):
        dm = data.models
        cls._init_models(dm)
        if dm.simulation.flashType == 'CapLaser':
            dm.IO.update(
                plot_var_5='magz',
                plot_var_6='depo',
            )

    @classmethod
    def proprietary_lib_file_basename(cls, data):
        return '{}.zip'.format(sirepo.util.secure_filename(data.models.simulation.flashType))

    @classmethod
    def _compute_job_fields(cls, data, r, compute_model):
        return [r]

    @classmethod
    def _lib_file_basenames(cls, data):
        t = data.models.simulation.flashType
        if t == 'RTFlame':
            return ['helm_table.dat']
        if t == 'CapLaser':
            return ['al-imx-004.cn4', 'h-imx-004.cn4']
        raise AssertionError('invalid flashType: {}'.format(t))
