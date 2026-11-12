"""Independent game-theory, information-boundary and real-engine checks."""
from dataclasses import asdict, replace
from itertools import product
import unittest

import numpy as np

from pokerlab.agent import Agent, Observation
from pokerlab.engine import play_hand
from pokerlab.research.policy import blueprints
from pokerlab.research.solver import ALGORITHMS, BucketGame, Solver
from pokerlab.strategies import all_strategies, selectable_strategies


def state(**updates):
    observation = Observation(('As', 'Qs'), ('Js', 'Ts', '2d', '3c', '9h'),
        1, 2, 2, 1200, 20, 300, 0, 0, 20, 1200, 1., 0, False, False,
        remaining=2, heads_up_in_position=True)
    return replace(observation, **updates)


class SolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.solvers = {a: Solver(BucketGame.kuhn(), a, seed=17).train(
            30000 if a == 'mccfr' else 3000) for a in ALGORITHMS}

    def test_kuhn_known_value_and_exploitability(self):
        for algorithm, solver in self.solvers.items():
            with self.subTest(algorithm=algorithm):
                result = solver.evaluate()
                self.assertAlmostEqual(result['value_p0'], -1/18,
                    delta=.004 if algorithm == 'mccfr' else .001)
                self.assertLess(result['exploitability'], .015 if algorithm == 'mccfr' else .001)

    def test_policy_probabilities_are_valid(self):
        for solver in self.solvers.values():
            for probabilities in solver.averaged().values():
                self.assertTrue(np.isfinite(probabilities).all())
                self.assertTrue((probabilities >= 0).all())
                np.testing.assert_allclose(probabilities.sum(axis=1), 1.)

    def test_best_response_matches_exhaustive_private_policies(self):
        # Six binary private information-set choices per player -> 64 policies.
        # Each choice is shared across all opponent cards: no hidden-card oracle.
        solver = Solver(BucketGame.kuhn()).train(7)
        policies = solver.averaged()
        def value(node, choices):
            if node.payoff is not None:
                return node.payoff
            probabilities = choices.get(id(node), policies[id(node)]).T
            children = np.array([value(c, choices) for c in node.children])
            return np.sum(children * (probabilities[:, :, None] if node.player == 0
                                      else probabilities[:, None, :]), axis=0)
        metrics = solver.evaluate(policies)
        for player in (0, 1):
            nodes = [n for n in solver.game.nodes if n.player == player]
            utilities = []
            for actions in product(range(2), repeat=3*len(nodes)):
                choices = {}
                for index, node in enumerate(nodes):
                    row = np.zeros((3, 2))
                    row[np.arange(3), actions[index*3:index*3+3]] = 1
                    choices[id(node)] = row
                u = float(np.sum(solver.game.chance * value(solver.game.root, choices)))
                utilities.append(u if player == 0 else -u)
            self.assertAlmostEqual(max(utilities), metrics[f'best_response_p{player}'], places=12)

    def test_independent_uniform_play_is_exploitable(self):
        solver = Solver(BucketGame.kuhn())
        self.assertGreater(solver.evaluate()['exploitability'], .3)

    def test_external_sampling_is_seed_reproducible(self):
        a = Solver(BucketGame.kuhn(), 'mccfr', seed=77).train(300)
        b = Solver(BucketGame.kuhn(), 'mccfr', seed=77).train(300)
        for left, right in zip(a.averaged().values(), b.averaged().values()):
            np.testing.assert_array_equal(left, right)

    def test_discount_and_prediction_equations(self):
        # A hand-calculated second update distinguishes regret discounting,
        # clipping, the optimistic predictor and average-strategy weighting.
        for algorithm in ('dcfr', 'pdcfr_plus', 'pcfr_plus'):
            solver = Solver(BucketGame.kuhn(), algorithm)
            key = id(solver.game.root)
            solver.iteration = 2
            solver.regret[key][:] = [2., -1.] if algorithm == 'dcfr' else [2., 0.]
            solver.average[key][:] = 4.
            solver.policy[key][:] = [.6, .4]
            solver.update(key, np.tile([1., 3.], (3, 1)), np.ones(3))
            regret = [2., 2.5] if algorithm == 'dcfr' else [2., 3.] if algorithm == 'pdcfr_plus' else [3., 3.]
            np.testing.assert_allclose(solver.regret[key], np.tile(regret, (3, 1)))
            if algorithm == 'pcfr_plus':
                np.testing.assert_allclose(solver.policy[key], np.tile([.4, .6], (3, 1)))
            gamma = 5 if algorithm == 'pdcfr_plus' else 2
            np.testing.assert_allclose(solver.average[key], np.tile(
                4*(.5**gamma)+np.array([.6, .4]), (3, 1)))


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = {s.id: s for s in selectable_strategies()}

    def test_registry_preserves_historical_experiment(self):
        self.assertEqual(len(all_strategies()), 80)
        self.assertEqual(len(self.registry), 90)
        self.assertEqual({s.research for s in self.registry.values() if s.research}, set(ALGORITHMS))

    def test_frozen_model_contains_public_history_policies(self):
        model = blueprints()
        self.assertEqual(model['schema_version'], 2)
        self.assertEqual(len(model['blueprints']), 36)
        for context in model['blueprints'].values():
            self.assertIn('r', context['nodes'])
            for node in context['nodes'].values():
                probabilities = np.asarray(node['probabilities'])
                self.assertEqual(probabilities.shape, (12, len(node['actions'])))
                np.testing.assert_allclose(probabilities.sum(axis=1), 1., atol=1e-8)
                self.assertTrue((probabilities >= 0).all())
                for child in node['children']:
                    self.assertTrue(child is None or child in context['nodes'])

    def test_opening_response_and_reraise_use_different_nodes(self):
        agent = Agent(self.registry['R03'])
        node_names = []
        for observation in (state(), state(to_call=100, pot=400),
                            state(to_call=100, bet=100, pot=600, stack=1100, max_raise_to=1200)):
            agent.decide(observation, .5)
            self.assertEqual(agent.last_details['policy_path'], 'research_blueprint')
            node_names.append(agent.last_details['public_node'])
        self.assertEqual(len(set(node_names)), 3)

    def test_out_of_position_histories_and_legal_sizes(self):
        for sid in (f'R{i:02}' for i in range(1, 7)):
            agent = Agent(self.registry[sid])
            for position in (False, True):
                for observation in (state(), state(to_call=100, pot=400),
                                    state(to_call=100, bet=100, pot=600, stack=1100, max_raise_to=1200)):
                    observation = replace(observation, heads_up_in_position=position)
                    for draw in (0., .25, .75, 1.):
                        action, amount = agent.decide(observation, draw)
                        self.assertIn(action, ('fold', 'call', 'raise'))
                        if action == 'raise':
                            self.assertGreaterEqual(amount, observation.min_raise_to)
                            self.assertLessEqual(amount, observation.max_raise_to)
                        if not observation.to_call:
                            self.assertNotEqual(action, 'fold')

    def test_unrepresented_states_explicitly_match_s55(self):
        agent = Agent(self.registry['R06']); baseline = Agent(self.registry['S55'])
        variants = {
            'preflop': state(board=()), 'multiway': state(players=6, active=3),
            'tournament': state(tournament=True),
            'unknown_position': state(players=6, heads_up_in_position=None),
            'off_grid_depth': state(stack=20000, max_raise_to=20000),
            'unrepresented_pot': state(pot=200, bet=100, to_call=100),
        }
        for reason, observation in variants.items():
            with self.subTest(reason=reason):
                self.assertEqual(agent.decide(observation, .37), baseline.decide(observation, .37))
                self.assertEqual(agent.last_details['policy_path'], 'fallback_'+reason)

    def test_closed_action_and_same_information_give_legal_reproducible_result(self):
        agent = Agent(self.registry['R05'])
        observation = state(to_call=100, pot=400, min_raise_to=None, max_raise_to=None)
        self.assertNotEqual(agent.decide(observation, .2)[0], 'raise')
        self.assertEqual(agent.decide(observation, .2), agent.decide(observation, .2))
        self.assertEqual(agent.decide(state(min_raise_to=None, max_raise_to=None)), ('call', 0))

    def test_real_holdem_hands_conserve_chips_and_never_receive_hidden_cards(self):
        modes = set()
        for sid in (f'R{i:02}' for i in range(1, 7)):
            for seed in range(18):
                result = play_hand([self.registry[sid], self.registry['S18']],
                    [2000, 2000], 20, seed+93000, trace=True)
                self.assertEqual(sum(result['after']), 4000)
                self.assertEqual(sum(result['net']), 0)
                for observation in result['observations']:
                    self.assertNotIn('holes', observation)
                    self.assertNotIn('deck', observation)
                    self.assertEqual(len(observation['hole']), 2)
                    self.assertIsInstance(observation['heads_up_in_position'], bool)
                modes.update(result['seat_modes'][0])
        self.assertIn('research_blueprint', modes)
        self.assertIn('fallback_preflop', modes)


if __name__ == '__main__':
    unittest.main()
