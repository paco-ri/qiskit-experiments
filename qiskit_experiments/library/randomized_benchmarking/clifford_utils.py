# This code is part of Qiskit.
#
# (C) Copyright IBM 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.
"""
Utilities for using the Clifford group in randomized benchmarking
"""

import warnings
from typing import Optional, Union, Sequence
from functools import lru_cache
import numpy as np
from numpy.random import Generator, default_rng
from qiskit import QuantumCircuit, QuantumRegister
from qiskit.circuit import Gate
from qiskit.circuit.library import SdgGate, HGate, SGate, SXdgGate
from qiskit.quantum_info import Clifford, random_clifford


class VGate(Gate):
    """V Gate used in Clifford synthesis."""

    def __init__(self):
        """Create new V Gate."""
        super().__init__("v", 1, [])

    def _define(self):
        """V Gate definition."""
        q = QuantumRegister(1, "q")
        qc = QuantumCircuit(q)
        qc.data = [(SdgGate(), [q[0]], []), (HGate(), [q[0]], [])]
        self.definition = qc


class WGate(Gate):
    """W Gate used in Clifford synthesis."""

    def __init__(self):
        """Create new W Gate."""
        super().__init__("w", 1, [])

    def _define(self):
        """W Gate definition."""
        q = QuantumRegister(1, "q")
        qc = QuantumCircuit(q)
        qc.data = [(HGate(), [q[0]], []), (SGate(), [q[0]], [])]
        self.definition = qc


class CliffordUtils:
    """Utilities for generating 1 and 2 qubit clifford circuits and elements"""

    NUM_CLIFFORD_1_QUBIT = 24
    NUM_CLIFFORD_2_QUBIT = 11520
    CLIFFORD_1_QUBIT_SIG = (2, 3, 4)
    CLIFFORD_2_QUBIT_SIGS = [
        (2, 2, 3, 3, 4, 4),
        (2, 2, 3, 3, 3, 3, 4, 4),
        (2, 2, 3, 3, 3, 3, 4, 4),
        (2, 2, 3, 3, 4, 4),
    ]

    def clifford_1_qubit(self, num):
        """Return the 1-qubit clifford element corresponding to `num`
        where `num` is between 0 and 23.
        """
        return Clifford(self.clifford_1_qubit_circuit(num), validate=False)

    def clifford_2_qubit(self, num):
        """Return the 2-qubit clifford element corresponding to `num`
        where `num` is between 0 and 11519.
        """
        return Clifford(self.clifford_2_qubit_circuit(num), validate=False)

    def random_cliffords(
        self, num_qubits: int, size: int = 1, rng: Optional[Union[int, Generator]] = None
    ):
        """Generate a list of random clifford elements"""
        if num_qubits > 2:
            return random_clifford(num_qubits, seed=rng)

        if rng is None:
            rng = default_rng()

        if isinstance(rng, int):
            rng = default_rng(rng)

        if num_qubits == 1:
            samples = rng.integers(24, size=size)
            return [Clifford(self.clifford_1_qubit_circuit(i), validate=False) for i in samples]
        else:
            samples = rng.integers(11520, size=size)
            return [Clifford(self.clifford_2_qubit_circuit(i), validate=False) for i in samples]

    def random_clifford_circuits(
        self, num_qubits: int, size: int = 1, rng: Optional[Union[int, Generator]] = None
    ):
        """Generate a list of random clifford circuits"""
        if num_qubits > 2:
            return [random_clifford(num_qubits, seed=rng).to_circuit() for _ in range(size)]

        if rng is None:
            rng = default_rng()

        if isinstance(rng, int):
            rng = default_rng(rng)

        if num_qubits == 1:
            samples = rng.integers(24, size=size)
            return [self.clifford_1_qubit_circuit(i) for i in samples]
        else:
            samples = rng.integers(11520, size=size)
            return [self.clifford_2_qubit_circuit(i) for i in samples]

    def random_edgegrab_clifford_circuits(
        self,
        qubits: Sequence[int],
        coupling_map: list,
        two_qubit_gate_density: float = 0.25,
        size: int = 1,
        rng: Optional[Union[int, Generator]] = None,
    ):
        """Generate a list of random Clifford circuits sampled using the edgegrab algorithm

        Ref: arXiv:2008.11294v2
        """
        num_qubits = len(qubits)
        # if circuit has one qubit, call random_clifford_circuits()
        if num_qubits == 1:
            return self.random_clifford_circuits(num_qubits, size, rng)

        if rng is None:
            rng = default_rng()

        if isinstance(rng, int):
            rng = default_rng(rng)

        qc_list = []
        for i in list(range(size)):
            all_edges = coupling_map[:]  # make copy of coupling map from which we pop edges
            selected_edges = []
            while all_edges:
                rand_edge = all_edges.pop(rng.integers(len(all_edges)))
                selected_edges.append(rand_edge)  # move random edge from B to A
                old_all_edges = all_edges[:]
                all_edges = []
                # only keep edges in B that do not share a vertex with rand_edge
                for edge in old_all_edges:
                    if rand_edge[0] not in edge and rand_edge[1] not in edge:
                        all_edges.append(edge)

            # A is reduced version of coupling map where each vertex appears maximally once
            qr = QuantumRegister(num_qubits)
            qc = QuantumCircuit(qr)
            two_qubit_prob = 0
            try:
                two_qubit_prob = num_qubits * two_qubit_gate_density / len(selected_edges)
            except ZeroDivisionError:
                warnings.warn(
                    "Device has no connectivity. All cliffords will be single-qubit Cliffords"
                )
            if two_qubit_prob > 1:
                warnings.warn(
                    "Mean number of two-qubit gates is higher than number of selected edges for CNOTs. "
                    + "Actual density of two-qubit gates will likely be lower than input density"
                )
            selected_edges_logical = [
                [np.where(q == np.asarray(qubits))[0][0] for q in edge] for edge in selected_edges
            ]
            # A_logical is A with logical qubit labels rather than physical ones:
            # Example: qubits = (8,4,5,3,7), A = [[4,8],[7,5]] ==> A_logical = [[1,0],[4,2]]
            put_1_qubit_clifford = np.arange(num_qubits)
            # put_1_qubit_clifford is a list of qubits that aren't assigned to a 2-qubit Clifford
            # 1-qubit Clifford will be assigned to these edges
            for edge in selected_edges_logical:
                if rng.random() < two_qubit_prob:
                    # with probability two_qubit_prob, place CNOT on edge in A
                    qc.cx(edge[0], edge[1])
                    # remove these qubits from put_1_qubit_clifford
                    put_1_qubit_clifford = np.setdiff1d(put_1_qubit_clifford, edge)
            for q in put_1_qubit_clifford:
                # pylint: disable=unbalanced-tuple-unpacking
                # copied from clifford_1_qubit_circuit() below
                (i, j, p) = self._unpack_num(rng.integers(24), self.CLIFFORD_1_QUBIT_SIG)
                if i == 1:
                    qc.h(q)
                if j == 1:
                    qc._append(SXdgGate(), [qr[q]], [])
                if j == 2:
                    qc._append(SGate(), [qr[q]], [])
                if p == 1:
                    qc.x(q)
                if p == 2:
                    qc.y(q)
                if p == 3:
                    qc.z(q)
            qc_list.append(qc)
        return qc_list

    @lru_cache(maxsize=24)
    def clifford_1_qubit_circuit(self, num):
        """Return the 1-qubit clifford circuit corresponding to `num`
        where `num` is between 0 and 23.
        """
        # pylint: disable=unbalanced-tuple-unpacking
        # This is safe since `_unpack_num` returns list the size of the sig
        (i, j, p) = self._unpack_num(num, self.CLIFFORD_1_QUBIT_SIG)
        qr = QuantumRegister(1)
        qc = QuantumCircuit(qr)
        if i == 1:
            qc.h(0)
        if j == 1:
            qc._append(SXdgGate(), [qr[0]], [])
        if j == 2:
            qc._append(SGate(), [qr[0]], [])
        if p == 1:
            qc.x(0)
        if p == 2:
            qc.y(0)
        if p == 3:
            qc.z(0)
        return qc

    @lru_cache(maxsize=11520)
    def clifford_2_qubit_circuit(self, num):
        """Return the 2-qubit clifford circuit corresponding to `num`
        where `num` is between 0 and 11519.
        """
        vals = self._unpack_num_multi_sigs(num, self.CLIFFORD_2_QUBIT_SIGS)
        qr = QuantumRegister(2)
        qc = QuantumCircuit(qr)
        if vals[0] == 0 or vals[0] == 3:
            (form, i0, i1, j0, j1, p0, p1) = vals
        else:
            (form, i0, i1, j0, j1, k0, k1, p0, p1) = vals
        if i0 == 1:
            qc.h(0)
        if i1 == 1:
            qc.h(1)
        if j0 == 1:
            qc.sxdg(0)
        if j0 == 2:
            qc.s(0)
        if j1 == 1:
            qc.sxdg(1)
        if j1 == 2:
            qc.s(1)
        if form in (1, 2, 3):
            qc.cx(0, 1)
        if form in (2, 3):
            qc.cx(1, 0)
        if form == 3:
            qc.cx(0, 1)
        if form in (1, 2):
            if k0 == 1:
                qc._append(VGate(), [qr[0]], [])
            if k0 == 2:
                qc._append(WGate(), [qr[0]], [])
            if k1 == 1:
                qc._append(VGate(), [qr[1]], [])
            if k1 == 2:
                qc._append(VGate(), [qr[1]], [])
                qc._append(VGate(), [qr[1]], [])
        if p0 == 1:
            qc.x(0)
        if p0 == 2:
            qc.y(0)
        if p0 == 3:
            qc.z(0)
        if p1 == 1:
            qc.x(1)
        if p1 == 2:
            qc.y(1)
        if p1 == 3:
            qc.z(1)
        return qc

    def _unpack_num(self, num, sig):
        r"""Returns a tuple :math:`(a_1, \ldots, a_n)` where
        :math:`0 \le a_i \le \sigma_i` where
        sig=:math:`(\sigma_1, \ldots, \sigma_n)` and num is the sequential
        number of the tuple
        """
        res = []
        for k in sig:
            res.append(num % k)
            num //= k
        return res

    def _unpack_num_multi_sigs(self, num, sigs):
        """Returns the result of `_unpack_num` on one of the
        signatures in `sigs`
        """
        for i, sig in enumerate(sigs):
            sig_size = 1
            for k in sig:
                sig_size *= k
            if num < sig_size:
                return [i] + self._unpack_num(num, sig)
            num -= sig_size
        return None

    def compute_target_bitstring(self, circuit: QuantumCircuit) -> str:
        """For a Clifford circuit C, compute C|0>.

        Args:
            circuit: A Clifford QuantumCircuit

        Returns:
            Target bit string
        """

        # convert circuit to Boolean phase vector of stabilizer table
        phase_vector = Clifford(circuit).table.phase
        n = circuit.num_qubits

        # target string has a 1 for each True in the stabilizer half of the phase vector
        target = "".join(["1" if phase else "0" for phase in phase_vector[n:][::-1]])
        return target
