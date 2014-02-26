#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
from . import utils
from itertools import chain


class Subsystem:

    """A set of nodes in a network.

    Acts as a candidate set for cause/effect repertoire calculation.

    """

    def __init__(self, nodes, current_state, past_state, network):
        """Initialize a Subsystem.

        :param nodes: A list of nodes in this subsystem
        :type nodes: ``[Node]``
        :param current_state: The current state of this subsystem
        :type current_state: ``np.ndarray``
        :param past_state: The past state of this subsystem
        :type past_state: ``np.ndarray``
        :param network: The network the subsystem is part of
        :type network: ``Network``

        """
        self.nodes = nodes

        self.current_state = current_state
        self.past_state = past_state
        # Make the state and past state immutable (for hashing)
        self.current_state.flags.writeable = False
        self.past_state.flags.writeable = False

        self.network = network

        # Nodes outside the subsystem will be treated as fixed boundary
        # conditions in cause/effect repertoire calculations
        self.external_nodes = set(network.nodes) - set(nodes)

    def __repr__(self):
        return "Subsystem(" + ", ".join([repr(self.nodes),
                                         repr(self.past_state),
                                         repr(self.current_state)]) + ")"

    def __str__(self):
        return "Subsystem([" + str(list(map(str, self.nodes))) + "]" + \
            ", " + str(self.current_state) + ", " + str(self.past_state) + \
            ", " + str(self.network) + ")"

    def __eq__(self, other):
        """
        Two subsystems are equal if their sets of nodes, current and past
        states, and networks are equal.
        """
        return (set(self.nodes) == set(other.nodes) and self.past_state ==
                other.past_state and self.current_state == other.past_state and
                self.network == other.network)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((frozenset(self.nodes), self.current_state.tostring(),
                     self.past_state.tostring(), self.network))

    def uc_cause_repertoire(self, purview):
        """Return the unconstrained past repertoire for the given purview.

        This is just the cause repertoire in the absence of any mechanism.
        """
        return self.cause_repertoire([], purview)

    def unconstrained_effect_repertoire(self, purview):
        """Return the unconstrained effect repertoire for the given purview.

        This is just the effect repertoire in the absence of any mechanism.
        """
        return self.effect_repertoire([], purview)

    def cause_repertoire(self, mechanism, purview):
        """Return the cause repertoire of this mechanism over the given
        purview.

        In the Matlab version's terminology,

        * *Cause repertoire* is "backward repertoire"
        * *Mechanism* is "numerator"
        * *Purview* is "denominator"
        * ``conditioned_tpm`` is ``next_num_node_distribution``
        * ``accumulated_cjd`` is ``numerator_conditional_joint``

        :param purview: The purview over which to calculate the cause
            repertoire
        :type purview: ``Subsystem``

        :returns: The cause repertoire of the mechanism over the given purview
        :rtype: ``np.ndarray``

        """
        # If the purview is empty, the distribution is empty
        if (len(purview) is 0):
            # TODO should this really be an empty array?
            return np.array([])

        # If the mechanism is empty, nothing is specified about the past state
        # of the purview, so just return the purview's maximum entropy
        # distribution
        if (len(mechanism) is 0):
            return utils.max_entropy_distribution(purview, self.network)

        # Preallocate the mechanism's conditional joint distribution
        # TODO extend to nonbinary nodes
        accumulated_cjd = np.ones(tuple(2 if node in purview else 1
                                        for node in self.network.nodes))
        # Loop over all nodes in this mechanism, successively taking the
        # product (with expansion/broadcasting of singleton dimensions) of each
        # individual node's CPT (conditioned on that node's state) in order to
        # get the conditional joint distribution for the whole mechanism
        # (conditioned on the whole mechanism's state). After normalization,
        # this is the cause repertoire. Normalization happens after this loop.
        future_nodes = mechanism
        past_nodes = purview
        for node in future_nodes:
            # TODO extend to nonbinary nodes
            # We're conditioning on this node's state, so take the
            # probabilities that correspond to that state (The TPM subtracted
            # from 1 gives the probability that the node is off).
            conditioned_tpm = (node.tpm if self.current_state[node.index] == 1
                               else 1 - node.tpm)
            # Marginalize-out the nodes with inputs to this mechanism that
            # aren't in the given purview
            # TODO explicit inputs to nodes (right now each node is implicitly
            # connected to all other nodes, since initializing a Network with a
            # connectivity matrix isn't implemented yet)
            for non_past_input in set(self.network.nodes) - set(past_nodes):
                                      # TODO add this when inputs are
                                      # implemented:
                                      # and node in self.input_nodes):
                # If the non-purview input node is part of the candidate
                # system, we marginalize it out of the current node's CPT.
                if non_past_input in self.nodes:
                    conditioned_tpm = utils.marginalize_out(non_past_input,
                                                            conditioned_tpm)
                # Now we condition the CPT on the past states of nodes outside
                # the candidate system, which we treat as fixed boundary
                # conditions. We collapse the dimensions corresponding to the
                # fixed nodes so they contain only the probabilities that
                # correspond to their past states.
                elif non_past_input not in self.nodes:
                    past_conditioning_indices = \
                        [slice(None)] * self.network.size
                    past_conditioning_indices[non_past_input.index] = \
                        [self.past_state[non_past_input.index]]
                    conditioned_tpm = \
                        conditioned_tpm[past_conditioning_indices]
            # Incorporate this node's CPT into the mechanism's conditional
            # joint distribution by taking the product (with singleton
            # broadcasting)
            accumulated_cjd = np.multiply(accumulated_cjd,
                                          conditioned_tpm)

        # Finally, normalize by the marginal probability of the past state to
        # get the mechanism's CJD
        accumulated_cjd_sum = np.sum(accumulated_cjd)
        # Don't divide by zero
        if accumulated_cjd_sum != 0:
            accumulated_cjd = (np.divide(accumulated_cjd,
                                         np.sum(accumulated_cjd)))

        # Note that we're not returning a distribution over all the nodes in
        # the network, only a distribution over the nodes in the purview. This
        # is because we never actually need to compare proper cause/effect
        # repertoires, which are distributions over the whole network; we need
        # only compare the purview-repertoires with each other, since cut vs.
        # whole comparisons are only ever done over the same purview.
        return accumulated_cjd

    def effect_repertoire(self, mechanism, purview):
        """Return the effect repertoire of this mechanism over the given
        purview.

        In the Matlab version's terminology,

        * *Effect repertoire* is "forward repertoire"
        * *Mechanism* is "numerator"
        * *Purview* is "denominator"
        * ``conditioned_tpm`` is ``next_denom_node_distribution``
        * ``accumulated_cjd`` is ``denom_conditional_joint``

        :param purview: The purview over which to calculate the effect
            repertoire
        :type purview: ``Subsystem``

        :returns: The effect repertoire of the mechanism over the given purview
        :rtype: ``np.ndarray``

        """
        # Preallocate the purview's joint distribution
        # TODO extend to nonbinary nodes
        accumulated_cjd = np.ones(tuple([1] * self.network.size +
                                        [2 if node in purview else 1
                                         for node in self.network.nodes]))
        # Loop over all nodes in the purview, successively taking the product
        # (with 'expansion'/'broadcasting' of singleton dimensions) of each
        # individual node's TPM in order to get the joint distribution for the
        # whole purview. After conditioning on the mechanism's state and that
        # of external nodes, this will be the effect repertoire as a
        # distribution over the purview.
        future_nodes = purview
        past_nodes = mechanism
        for node in future_nodes:
            # Unlike in calculating the cause repertoire, here the TPM is not
            # conditioned yet. `tpm` is an array with twice as many dimensions
            # as the network has nodes. For example, in a network with three
            # nodes {n0, n1, n2}, the CPT for node n1 would have shape
            # (2,2,2,1,2,1). The CPT for the node being off would be given by
            # `tpm[:,:,:,0,0,0]`, and the CPT for the node being on would be
            # given by `tpm[:,:,:,0,1,0]`. The second half of the shape is for
            # indexing based on the current node's state, and the first half of
            # the shape is the CPT indexed by network state, so that the
            # overall CPT can be broadcast over the `accumulated_cjd` and then
            # later conditioned by indexing.

            # TODO extend to nonbinary nodes
            # Allocate the TPM
            tpm = np.zeros([2] * self.network.size +
                           [2 if i is node.index else 1 for i in
                            range(self.network.size)])
            tpm_off_indices = [slice(None)] * self.network.size + \
                [0] * self.network.size
            # Insert the TPM for the node being off
            tpm[tpm_off_indices] = 1 - node.tpm
            # Insert the TPM for the node being on
            tpm_on_indices = [slice(None)] * self.network.size + \
                [1 if i == node.index else 0 for i in
                 range(self.network.size)]
            tpm[tpm_on_indices] = node.tpm

            # Marginalize-out the subsystem nodes with inputs to the purview
            # that aren't in the mechanism
            # TODO explicit inputs to nodes (right now each node is implicitly
            # connected to all other nodes, since initializing a Network with a
            # connectivity matrix isn't implemented yet)
            for non_past_input in set(self.nodes) - set(past_nodes):
                                   # TODO add this when inputs are implemented:
                                   # and node in self.input_nodes):
                tpm = utils.marginalize_out(non_past_input, tpm)

            # Incorporate this node's CPT into the future_nodes' conditional
            # joint distribution by taking the product (with singleton
            # broadcasting)
            accumulated_cjd = np.multiply(accumulated_cjd, tpm)

        # Now we condition on the state of the past nodes and the external
        # nodes (by collapsing the CJD onto those states).

        # Initialize the conditioning indices, taking the slices as singleton
        # lists-of-lists for later flattening with `chain`.
        conditioning_indices = [[slice(None)]] * self.network.size
        for node in set(past_nodes) | set(self.external_nodes):
            # Preserve singleton dimensions with `np.newaxis`
            conditioning_indices[node.index] = [self.current_state[node.index],
                                                np.newaxis]
        # Flatten the indices
        conditioning_indices = list(chain.from_iterable(conditioning_indices))

        # Obtain the actual conditioned distribution by indexing with the
        # conditioning indices
        accumulated_cjd = accumulated_cjd[tuple(conditioning_indices)]
        # The distribution still has twice as many dimensions as the network
        # has nodes, with the first half of the shape now all singleton
        # dimesnions, so we reshape to eliminate those singleton dimensions
        # (the second half of the shape may also contain singleton dimensions,
        # depending on how many nodes are in the purview).
        accumulated_cjd = accumulated_cjd.reshape(
            accumulated_cjd.shape[self.network.size:2 * self.network.size])

        # Note that we're not returning a distribution over all the nodes in
        # the network, only a distribution over the nodes in the purview. This
        # is because we never actually need to compare proper cause/effect
        # repertoires, which are distributions over the whole network; we need
        # only compare the purview-repertoires with each other, since cut vs.
        # whole comparisons are only ever done over the same purview.
        return accumulated_cjd
