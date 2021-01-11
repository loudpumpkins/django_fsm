from inspect import isfunction, ismethod, getmembers
from django.db import models
from django.db.models.signals import class_prepared
from django.dispatch import Signal


transition = Signal(providing_args=['instance', 'name', 'source', 'destination', 'exception'])


class TransitionNotAllowed(Exception):
	"""
	Raised when a transition is not allowed
	"""


class ONE_OF(object):
	"""
	Accepts of a list of allowed destinations
	"""
	def __init__(self, *allowed_states):
		if len(allowed_states) == 0:
			raise ValueError('ONE_OF() must receive at least one destination.')
		if type(allowed_states[0]) is str:
			# args contains multiple strings
			self.allowed_states = allowed_states
		elif type(allowed_states[0]) in [list, tuple]:
			# args is a list of strings
			self.allowed_states = tuple(allowed_states[0])

	def get_state(self, result):
		if result not in self.allowed_states:
			raise TransitionNotAllowed(
				f'{result} is not in list of allowed states\n{self.allowed_states}')
		return result


class FSMFieldDescriptor(object):
	"""
	Field descriptor will prevent direct modification of the state field if set
	to ``readonly``.

	https://docs.python.org/3/howto/descriptor.html
	"""
	def __init__(self, field):
		self.field = field
		self.private_field_name = f'__fsm_{field.name}'

	def __get__(self, model, objtype=None):
		if model is None:
			# None when the attribute is accessed through the class (type(model))
			# return the descriptor itself
			return self
		return getattr(model, self.private_field_name)

	def __set__(self, model, value):
		if self.field.readonly and hasattr(model, self.private_field_name):
			raise AttributeError(f"Field {self.field.name} is set to `readonly` "
			                     f"and thus direct modification is not allowed")
		setattr(model, self.private_field_name, value)


class FSMField(models.CharField):
	"""
	State Machine support for Django model as CharField,

	https://docs.djangoproject.com/en/2.1/howto/custom-model-fields
	"""
	def __init__(self, readonly=True, max_length=60, *args, **kwargs):
		self.readonly = readonly
		self.parent_cls = None
		super().__init__(max_length=max_length, *args, **kwargs)

	def deconstruct(self):
		"""
		Used in django migration to reconstruct the field -- reverse of __init__()

		https://docs.djangoproject.com/en/2.1/howto/custom-model-fields/#field-deconstruction
		"""
		name, path, args, kwargs = super().deconstruct()
		if self.readonly:
			kwargs['readonly'] = self.readonly
		return name, path, args, kwargs

	def get_state(self, model):
		"""
		Circumvent the model's FSMFieldDescriptor

		:param model: instance of model that owns the field
		"""
		return getattr(model, f'__fsm_{self.name}')

	def set_state(self, model, state):
		"""
		Circumvent the model's FSMFieldDescriptor

		:param model: instance of model that owns the field
		:param state: str: desired state
		"""
		setattr(model, f'__fsm_{self.name}', state)

	def change_state(self, method_owner, method, *args, **kwargs):
		"""
		Method used to drive the @transition decorated method.

		:param method_owner: instance of the class that owns the @transition
			decorated method. Usually an instance of the model that also owns
			the field.

		:param method: @transition decorated method. Must return a string of the
			next state if the destination has multiple possible targets or
			NoReturn otherwise.

		:param args: @transition decorated method args

		:param kwargs: @transition decorated method kwargs

		:return: the result of the @transition decorated method
		"""
		fsm_tag = method._fsm_tag
		method_name = method.__name__
		current_state = self.get_state(method_owner)

		if not fsm_tag.has_transition(current_state):
			raise TransitionNotAllowed(
				f"Can't switch from state '{current_state}' using method "
				f"'{method_name}'")
		if not fsm_tag.conditions_met(method_owner, current_state):
			raise TransitionNotAllowed(
				f"Transition conditions have not been met for method "
				f"'{method_name}'")

		next_state = fsm_tag.next_state(current_state)

		signal_kwargs = {
			'sender': method_owner.__class__,
			'instance': method_owner,
			'name': method_name,
			'field': fsm_tag.field,
			'source': current_state,
			'destination': next_state,
			'exception': None,
			'method_args': args,
			'method_kwargs': kwargs
		}

		try:
			result = method(method_owner, *args, **kwargs)  # method(self, *args, **kwargs)
			if next_state is not None:
				if isinstance(next_state, ONE_OF):
					next_state = next_state.get_state(result)
					signal_kwargs['destination'] = next_state
				self.set_state(method_owner, next_state)
		except Exception as exc:
			exception_state = fsm_tag.exception_state(current_state)
			if exception_state:
				self.set_state(method_owner, exception_state)
				signal_kwargs['destination'] = exception_state
				signal_kwargs['exception'] = exc
				transition.send(**signal_kwargs)
			raise
		else:
			transition.send(**signal_kwargs)

		return result

	def contribute_to_class(self, cls, name, private_only=False):
		"""
		ModelBase class calls this method during model construction that we can
		use to inject the field descriptor into the Model that owns this field.

		http://lazypython.blogspot.com/2008/11/django-models-digging-little-deeper.html

		:param cls: model class that owns the field
		:param name: state field name
		"""
		super().contribute_to_class(cls, name, private_only)
		setattr(cls, name, FSMFieldDescriptor(self))

		self.parent_cls = cls
		class_prepared.connect(self.assign_field_to_tag)

	def assign_field_to_tag(self, sender, **kwargs):
		"""
		Each transition decorated method is tagged with meta data named `_fsm_tag`
		with a `field` attribute. In the event that the `field` is left as a string,
		this method will replace it with the `field` object instead.
		"""
		if self.parent_cls is None or not issubclass(sender, self.parent_cls):
			return

		for _, value in getmembers(sender):
			if (ismethod(value) or isfunction(value)) and hasattr(value, '_fsm_tag'):
				if value._fsm_tag.field == self.name:
					# Assign the field object if the sender is the field's owner
					# and the field name is this field's name.
					value._fsm_tag.field = self
