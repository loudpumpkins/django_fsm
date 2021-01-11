from functools import wraps


class TransitionNotAllowed(Exception):
	"""
	Raised when a transition is not allowed
	"""


class FSMTag(object):
	"""
	Each transition decorated method will be tagged with an FSMTag attribute. The
	tag identifies the method as a transition method and it holds a reference to
	the field that holds the state and the transitions.
	"""
	def __init__(self, field):
		self.field = field  # field that holds the state and state_change method
		self.transitions = {}  # dict{ source : dict{ membr.name: membr.value } }

	def get_transition(self, source):
		"""
		Get all possible `destinations` from given `source`.
		:param src: str: source
		:return: Transition
		"""
		transition = self.transitions.get(source, None)
		if transition is None:
			transition = self.transitions.get('*', None)
		if transition is None:
			transition = self.transitions.get('+', None)
		return transition

	def add_transition(self, source, destination, on_error=None, conditions=[], custom={}):
		"""
		Append a dictionary to `self.transitions` with the source's transition
		information. A dictionary is created for each source.

		:param source: str: source of allowed transitions
		:param destination: str: destination of allowed transitions
		:param on_error: func: callback to run upon error
		:param conditions: list[func]: tests that need to pass to transition
		:param custom: Not yet used
		:return:
		"""
		if source in self.transitions:
			raise AssertionError('Duplicate transition for {0} state'.format(source))

		self.transitions[source] = {
			'source': source,
			'destination': destination,
			'on_error': on_error,
			'conditions': conditions,
			'custom': custom
		}

	def has_transition(self, state):
		"""
		Check if the given state has a transition to make.
		"""
		if state in self.transitions:
			return True

		if '*' in self.transitions:
			return True

		if '+' in self.transitions and self.transitions['+'].target != state:
			return True

		return False

	def conditions_met(self, method_owner, state):
		"""
		Check if all conditions have been met

		:param method_owner: usually the instance of the model that owns the
			method and the field.
		:param state: str: current state.
		"""
		transition = self.get_transition(state)

		if transition is None:
			return False
		elif transition['conditions'] is None:
			return True
		else:
			return all(map(lambda condition: condition(method_owner), transition['conditions']))

	def next_state(self, current_state):
		transition = self.get_transition(current_state)

		if transition is None:
			raise TransitionNotAllowed('No transition from {0}'.format(current_state))

		return transition['destination']

	def exception_state(self, current_state):
		transition = self.get_transition(current_state)

		if transition is None:
			raise TransitionNotAllowed('No transition from {0}'.format(current_state))

		return transition['on_error']


def transition(src='*', dest=None, field='state', on_error=None, conditions=[], custom={}):
	"""
	Tag the function with an `_fsm_tag` attribute which will be used to identify
	the function as a transition function.

	Set destination to None if current state needs to be validated and
	has not changed after the function call.

	:param src: U(str, list[str]): allowed sources from which transitions are
		allowed. May set as `*` for all sources allowed or `+` for all sources
		allowed, but the destination must not equal the source.

	:param dest: U(str, ONE_OF()): allowed destinations from the given
		source(s). Does NOT accept a list of destinations, but if multiple
		destinations are allowed, use an instance of `ONE_OF(list)` where list
		in an array of allowed destinations. eg: `dest=ONE_OF(['approved', 'denied'])

	:param field: U(str, FSMField): field or the name of the field that holds
		the state of the object.

	:param on_error: str: in the event that the `src` is valid, but the transition
		failed with an exception, set the `state` to `on_error` state. A `transition`
		signal will be dispatched with `signal_kwargs['exception']` set to the
		exception for investigation. If set to `None`, no state change will occur
		in the event of an error.

	:param conditions: list[func]: a list of functions that will be executed and
		must all evaluate to `True` for the transition to occur. Otherwise,

	:param custom:

	:return:
	"""
	def internal_method(method):
		fsm_tag = FSMTag(field=field)
		setattr(method, '_fsm_tag', fsm_tag)

		if isinstance(src, (list, tuple, set)):
			for state in src:
				method._fsm_tag.add_transition(state, dest, on_error, conditions, custom)
		else:
			method._fsm_tag.add_transition(src, dest, on_error, conditions, custom)

		@wraps(method)
		def _change_state(method_owner, *args, **kwargs):
			return fsm_tag.field.change_state(method_owner, method, *args, **kwargs)

		return _change_state

	return internal_method
