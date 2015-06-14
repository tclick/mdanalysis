# -*- Mode: python; tab-width: 4; indent-tabs-mode:nil; coding:utf-8 -*-
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 fileencoding=utf-8
#
# MDAnalysis --- http://www.MDAnalysis.org
# Copyright (c) 2006-2015 Naveen Michaud-Agrawal, Elizabeth J. Denning, Oliver Beckstein
# and contributors (see AUTHORS for the full list)
#
# Released under the GNU Public Licence, v2 or any higher version
#
# Please cite your use of MDAnalysis in published work:
#
# N. Michaud-Agrawal, E. J. Denning, T. B. Woolf, and O. Beckstein.
# MDAnalysis: A Toolkit for the Analysis of Molecular Dynamics Simulations.
# J. Comput. Chem. 32 (2011), 2319--2327, doi:10.1002/jcc.21787

# TRZ Reader written by Richard J. Gowers (2013)

"""TRZ trajectory I/O  --- :mod:`MDAnalysis.coordinates.TRZ`
============================================================

Classes to read `IBIsCO`_ / `YASP`_ binary trajectories.

Reads coordinates, velocities and more (see attributes of the
:class:`Timestep`).

.. _IBIsCO: http://www.theo.chemie.tu-darmstadt.de/ibisco/IBISCO.html
.. _YASP: http://www.theo.chemie.tu-darmstadt.de/group/services/yaspdoc/yaspdoc.html

.. autoclass:: MDAnalysis.coordinates.TRZ.Timestep
   :members:

   .. attribute:: frame

      Index of current frame number (1 based)

   .. attribute:: time

      Current system time in ps

   .. attribute:: numatoms

      Number of atoms in the frame (will be constant throughout trajectory)

   .. attribute:: pressure

      System pressure in pascals

   .. attribute:: pressure_tensor

      Array containing pressure tensors in order: xx, xy, yy, xz, yz, zz

   .. attribute:: total_energy

      Hamiltonian for the system in kJ/mol

   .. attribute:: potential_energy

      Potential energy of the system in kJ/mol

   .. attribute:: kinetic_energy

      Kinetic energy of the system in kJ/mol

   .. attribute:: temperature

      Temperature of the system in Kelvin

.. autoclass:: TRZReader
   :members:

.. autoclass:: TRZWriter
   :members:
"""

from sys import maxint
import numpy as np
import os
import errno

from . import base
import MDAnalysis.core
import MDAnalysis.core.util as util
from .core import triclinic_box


class Timestep(base.Timestep):
    """ TRZ custom Timestep"""
    def _init_unitcell(self):
        return np.zeros(9)

    @property
    def dimensions(self):
        """
        Unit cell dimensions ``[A,B,C,alpha,beta,gamma]``.
        """
        x = self._unitcell[0:3]
        y = self._unitcell[3:6]
        z = self._unitcell[6:9]
        return triclinic_box(x, y, z)

    @dimensions.setter
    def dimensions(self, box):
        """Set the Timestep dimensions with MDAnalysis format cell
        (*A*, *B*, *C*, *alpha*, *beta*, *gamma*)

        .. versionadded:: 0.9.0
        """
        if len(box) == 3 or len(box) == 6:
            self._unitcell[0] = box[0]
            self._unitcell[4] = box[1]
            self._unitcell[8] = box[2]
        else:
            raise ValueError("Must set using MDAnalysis format box")


class TRZReader(base.MultiframeReader):
    """ Reads an IBIsCO or YASP trajectory file

    :Data:
        ts
          :class:`~MDAnalysis.coordinates.TRZ.Timestep` object
          containing coordinates of current frame

    :Methods:
      ``len(trz)``
        returns the number of frames
      ``for ts in trz``
        iterates through the trajectory
      ``for ts in trz[start:stop:skip]``
        iterate through a trajectory using slicing
      ``trz[i]``
        random access of a trajectory frame
    """

    format = "TRZ"

    units = {'time': 'ps', 'length': 'nm', 'velocity': 'nm/ps'}

    def __init__(self, filename, numatoms=None, convert_units=None, **kwargs):
        """Creates a TRZ Reader

        :Arguments:
          *filename*
            name of input file
          *numatoms*
            number of atoms in trajectory, must taken from topology file!
          *convert_units*
            converts units to MDAnalysis defaults
        """
        if numatoms is None:
            raise ValueError('TRZReader requires the numatoms keyword')

        if convert_units is None:
            convert_units = MDAnalysis.core.flags['convert_lengths']
        self.convert_units = convert_units

        self.filename = filename

        self._numatoms = numatoms
        self.fixed = False
        self.periodic = True
        self.skip = 1
        self._numframes = None
        self._delta = None
        self._dt = None
        self._skip_timestep = None

        self._read_header()
        self.ts = Timestep(self.numatoms, velocities=True, forces=self.has_force)

        # structured dtype of a single trajectory frame
        readarg = str(numatoms) + 'f4'
        frame_contents = [
            ('p1', 'i4'),
            ('nframe', 'i4'),
            ('ntrj', 'i4'),
            ('natoms', 'i4'),
            ('treal', 'f8'),
            ('p2', '2i4'),
            ('box', '9f8'),
            ('p3', '2i4'),
            ('pressure', 'f8'),
            ('ptensor', '6f8'),
            ('p4', '3i4'),
            ('etot', 'f8'),
            ('ptot', 'f8'),
            ('ek', 'f8'),
            ('T', 'f8'),
            ('p5', '6i4'),
            ('rx', readarg),
            ('pad2', '2i4'),
            ('ry', readarg),
            ('pad3', '2i4'),
            ('rz', readarg),
            ('pad4', '2i4'),
            ('vx', readarg),
            ('pad5', '2i4'),
            ('vy', readarg),
            ('pad6', '2i4'),
            ('vz', readarg)]
        if not self.has_force:
            frame_contents += [('pad7', 'i4')]
        else:
            frame_contents += [
                ('pad7', '2i4'),
                ('fx', readarg),
                ('pad8', '2i4'),
                ('fy', readarg),
                ('pad9', '2i4'),
                ('fz', readarg),
                ('pad10', 'i4')]
        self._dtype = np.dtype(frame_contents)

        self.next()

    def _read_header(self):
        """Reads the header of the trz trajectory"""
        with open(self.filename, 'rb') as f:
            self._headerdtype = np.dtype([
                ('p1', 'i4'),
                ('title', '80c'),
                ('p2', '2i4'),
                ('force', 'i4'),
                ('p3', 'i4')])
            data = np.fromfile(f, dtype=self._headerdtype, count=1)
            self._start_pos = self._previous_pos = f.tell()
        self.title = ''.join(data['title'][0])



        if data['force'] == 10:
            self.has_force = False
        elif data['force'] == 20:
            self.has_force = True
        else:
            raise ValueError("Unrecognised value, possibly not a TRZ")

    def _read_next_timestep(self, ts=None):
        if ts is None:
            ts = self.ts

        try:
            data = np.fromfile(self._f, dtype=self._dtype, count=1)
            ts.frame = data['nframe'][0]
            ts.step = data['ntrj'][0]
            ts.time = data['treal'][0]
            ts._unitcell[:] = data['box']
            ts.pressure = data['pressure']
            ts.pressure_tensor = data['ptensor']
            ts.total_energy = data['etot']
            ts.potential_energy = data['ptot']
            ts.kinetic_energy = data['ek']
            ts.temperature = data['T']
            ts._x[:] = data['rx']
            ts._y[:] = data['ry']
            ts._z[:] = data['rz']
            ts._velocities[:, 0] = data['vx']
            ts._velocities[:, 1] = data['vy']
            ts._velocities[:, 2] = data['vz']
            if self.has_force:
                ts._forces[:, 0] = data['fx']
                ts._forces[:, 1] = data['fy']
                ts._forces[:, 2] = data['fz']
        except IndexError: # Raises indexerror if data has no data (EOF)
            raise IOError
        else:
            # Convert things read into MDAnalysis' native formats (nm -> angstroms)
            if self.convert_units:
                self.convert_pos_from_native(self.ts._pos)
                self.convert_pos_from_native(self.ts._unitcell)
                self.convert_velocities_from_native(self.ts._velocities)

            return ts

    @property
    def numatoms(self):
        """Number of atoms in a frame"""
        return self._numatoms

    @property
    def numframes(self):
        """Total number of frames in a trajectory"""
        if not self._numframes is None:
            return self._numframes
        try:
            self._numframes = self._read_trz_numframes()
        except IOError:
            return 0
        else:
            return self._numframes

    def _read_trz_numframes(self):
        """Uses size of file and dtype information to determine how many frames exist

        .. versionchanged:: 0.9.0
           Now is based on filesize rather than reading entire file
        """
        # size of file in bytes
        with open(self.filename, 'rb') as f:
            fsize = os.fstat(f.fileno()).st_size

        if (fsize - self._headerdtype.itemsize) % self._dtype.itemsize:
            raise IOError("Trajectory has incomplete frames")

        nframes = int((fsize - self._headerdtype.itemsize) / self._dtype.itemsize)  # returns long int otherwise

        return nframes

    @property
    def dt(self):
        """The amount of time between frames in ps

        Assumes that this step is constant (ie. 2 trajectories with different steps haven't been
        stitched together)
        Returns 0 in case of IOError
        """
        if not self._dt is None:
            return self._dt
        try:
            t0 = self.ts.time
            self.next()
            t1 = self.ts.time
            self._dt = t1 - t0
        except IOError:
            return 0
        finally:
            self.rewind()
        return self._dt

    @property
    def delta(self):
        """MD integration timestep"""
        if not self._delta is None:
            return self._delta
        self._delta = self.dt / self.skip_timestep
        return self._delta

    @property
    def skip_timestep(self):
        """Timesteps between trajectory frames"""
        if not self._skip_timestep is None:
            return self._skip_timestep
        try:
            t0 = self.ts.step
            self.next()
            t1 = self.ts.step
            self._skip_timestep = t1 - t0
        except IOError:
            return 0
        finally:
            self.rewind()
        return self._skip_timestep

    def _read_frame(self, frame):
        """Move to *frame* and return that Timestep."""
        newpos = self._headerdtype.itemsize 
        newpos += frame * self._dtype.itemsize
        self._previous_pos = newpos
        return self.next()

    def _reopen(self):
        self.close()
        self._previous_pos = self._start_pos
        ts = self.ts
        ts.status = 1
        ts.frame = 0
        ts.step = 0
        ts.time = 0

    def Writer(self, filename, numatoms=None):
        if numatoms is None:
            # guess that they want to write the whole timestep unless told otherwise?
            numatoms = self.ts.numatoms
        return TRZWriter(filename, numatoms)


class TRZWriter(base.Writer):
    """Writes a TRZ format trajectory.

    :Methods:
       ``W = TRZWriter(trzfilename, numatoms, title='TRZ')``
    """

    format = 'TRZ'

    units = {'time': 'ps', 'length': 'nm', 'velocity': 'nm/ps'}

    def __init__(self, filename, numatoms, title='TRZ', convert_units=None):
        """Create a TRZWriter

        :Arguments:
         *filename*
          name of output file
         *numatoms*
          number of atoms in trajectory

        :Keywords:
         *title*
          title of the trajectory
         *convert_units*
          units are converted to the MDAnalysis base format; ``None`` selects
          the value of :data:`MDAnalysis.core.flags` ['convert_lengths'].
          (see :ref:`flags-label`)
        """
        self.filename = filename
        if numatoms is None:
            raise ValueError("TRZWriter requires the numatoms keyword")
        if numatoms == 0:
            raise ValueError("TRZWriter: no atoms in output trajectory")
        self.numatoms = numatoms

        if convert_units is None:
            convert_units = MDAnalysis.core.flags['convert_lengths']
        self.convert_units = convert_units

        self.trzfile = util.anyopen(self.filename, 'wb')

        self._writeheader(title)

        floatsize = str(numatoms) + 'f4'
        self.frameDtype = np.dtype([
            ('p1a', 'i4'),
            ('nframe', 'i4'),
            ('ntrj', 'i4'),
            ('natoms', 'i4'),
            ('treal', 'f8'),
            ('p1b', 'i4'),
            ('p2a', 'i4'),
            ('box', '9f8'),
            ('p2b', 'i4'),
            ('p3a', 'i4'),
            ('pressure', 'f8'),
            ('ptensor', '6f8'),
            ('p3b', 'i4'),
            ('p4a', 'i4'),
            ('six', 'i4'),
            ('etot', 'f8'),
            ('ptot', 'f8'),
            ('ek', 'f8'),
            ('T', 'f8'),
            ('blanks', '2f8'),
            ('p4b', 'i4'),
            ('p5a', 'i4'),
            ('rx', floatsize),
            ('p5b', 'i4'),
            ('p6a', 'i4'),
            ('ry', floatsize),
            ('p6b', 'i4'),
            ('p7a', 'i4'),
            ('rz', floatsize),
            ('p7b', 'i4'),
            ('p8a', 'i4'),
            ('vx', floatsize),
            ('p8b', 'i4'),
            ('p9a', 'i4'),
            ('vy', floatsize),
            ('p9b', 'i4'),
            ('p10a', 'i4'),
            ('vz', floatsize),
            ('p10b', 'i4')])

    def _writeheader(self, title):
        hdt = np.dtype([
            ('pad1', 'i4'), ('title', '80c'), ('pad2', 'i4'),
            ('pad3', 'i4'), ('nrec', 'i4'), ('pad4', 'i4')])
        out = np.zeros((), dtype=hdt)
        out['pad1'], out['pad2'] = 80, 80
        out['title'] = title
        out['pad3'], out['pad4'] = 4, 4
        out['nrec'] = 10
        out.tofile(self.trzfile)

    def write_next_timestep(self, ts):
        # Check size of ts is same as initial
        if not ts.numatoms == self.numatoms:
            raise ValueError("Number of atoms in ts different to initialisation")

        out = np.zeros((), dtype=self.frameDtype)
        out['p1a'], out['p1b'] = 20, 20
        out['nframe'] = ts.frame
        out['ntrj'] = ts.step
        out['treal'] = ts.time
        out['p2a'], out['p2b'] = 72, 72
        out['box'] = self.convert_pos_to_native(ts._unitcell, inplace=False)
        out['p3a'], out['p3b'] = 56, 56
        out['pressure'] = ts.pressure
        out['ptensor'] = ts.pressure_tensor
        out['p4a'], out['p4b'] = 60, 60
        out['six'] = 6
        out['etot'] = ts.total_energy
        out['ptot'] = ts.potential_energy
        out['ek'] = ts.kinetic_energy
        out['T'] = ts.temperature
        out['blanks'] = 0.0, 0.0
        size = ts.numatoms * 4  # size of float for vels & coords
        out['p5a'], out['p5b'] = size, size
        out['rx'] = self.convert_pos_to_native(ts._x, inplace=False)
        out['p6a'], out['p6b'] = size, size
        out['ry'] = self.convert_pos_to_native(ts._y, inplace=False)
        out['p7a'], out['p7b'] = size, size
        out['rz'] = self.convert_pos_to_native(ts._z, inplace=False)
        out['p8a'], out['p8b'] = size, size
        out['vx'] = self.convert_velocities_to_native(ts._velocities[:, 0], inplace=False)
        out['p9a'], out['p9b'] = size, size
        out['vy'] = self.convert_velocities_to_native(ts._velocities[:, 1], inplace=False)
        out['p10a'], out['p10b'] = size, size
        out['vz'] = self.convert_velocities_to_native(ts._velocities[:, 2], inplace=False)
        out.tofile(self.trzfile)

    def close(self):
        """Close if it was open"""
        if self.trzfile is None:
            return
        self.trzfile.close()
        self.trzfile = None
