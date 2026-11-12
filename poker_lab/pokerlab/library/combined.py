"""T04: the three reference policies composed by scope."""
from . import Policy,register
from .pushfold import NashPushFold
from .positional import PositionalOpen
from .mdf import MdfGeometric


@register('T04','Theory baseline · charts, MDF and Nash jams',
          'T01 + T02 + T03 composed; see each source',
          'Each component in its own scope; remaining spots S55')
class TheoryBaseline(Policy):
    def __init__(self):
        super().__init__()
        self.parts=[NashPushFold(),PositionalOpen(),MdfGeometric()]

    def decide(self,o,draw):
        for part in self.parts:
            action=part.decide(o,draw)
            if not part.details.get('policy_path','').startswith('fallback_'):
                self.details=dict(part.details,component=type(part).__name__)
                return action
        self.details=dict(self.parts[-1].details)
        return action
