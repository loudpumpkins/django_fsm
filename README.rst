Django finite state machine add-on
==================================

Add's ``state`` field to DJango models which can transition from one state to
another through decorative ``transition`` methods. Set allowed source,
destination and conditions to the transition.

Allows for easy state management of DJango objects and prevents state change
if all conditions are not met.

Usage
------------

git clone project into the same directory as ``manage.py``

Usage of Django fsm has two critical components. The FSMField and @transition
decorated methods. They would typically both reside in the same model, but may
also be inherited, or injected in a meta class.

FSMField
________

By default, this field should be named ``state``. This way, it does not need to be
specified in each transition method. But in the case that a model has multiple
finite state machines to manage, it can be renamed.

.. code-block:: python

    state = FSMField(
        default='unpaid',
        choices=('unpaid', 'paid', 'refunded')
        readonly=True,
    )

:default:     default state of the object
:choices:     list/tuple of the possible states of the object
:readonly:    bool; prevent direct manipulation of the state (default True)

@transition
___________

@transition decorated methods are the methods called when a transition is required.
The decorated method should return None (or NoReturn) or a string representation
of the next state in the event that a state has multiple possible paths.

.. code-block:: python

    @transition(src='*', dest=None, field='state', on_error=None, conditions=[], custom={}):
    def traverse(self):
        pass

:src:       The state that a transition is allowed to originate from. By default,
            it is set to ``'*'`` which means that it may transition to the given
            destination from anywhere.
            ``'+'`` is an acceptable argument for src and means that a transition
            may occur from any source, but must land on a destination disjoint
            from the source.
            Otherwise, a string or a list of strings of allowed sources is accepted
            which denotes all the states a transition can originate from.
:dest:      The allowed destinations from the given source(s). Does NOT accept a
            list of destinations, but if multiple destinations are allowed, use
            an instance of ``ONE_OF(list)`` where list is an array of allowed
            destinations. eg: `dest=ONE_OF(['approved', 'denied'])`.
:field:     By default, the field is set to ``'field'`` but accepts the ``FSMField``
            object or the FSMField.name string of the model that holds the state.
:on_error:  In the event that the ``src`` is valid, but the transition failed with
            an exception, set the ``state`` to ``on_error`` state. A ``transition``
            signal will be dispatched with ``signal_kwargs['exception']`` set to
            the exception for investigation.
            By default, ``on_error`` is set to ``None`` which will not change the
            ``state`` of the model upon raised exceptions.
:conditions: A list of functions that must evaluate to ``True`` in order for the
            transition to occur. In the event that a condition fails, an exception
            is raised (``TransitionNotAllowed`` exception).
            If No conditions are provided, the transition will occur upon method
            call.
:custom:    Not yet used, will be used to integrate the FSMField into adminModel.

Simple Example
--------------

in models.py

.. code-block:: python

    from django_fsm import FSMField, transition

    class Order(models.Model):
        state = FSMField(
            default='unpaid',
            verbose_name='Order Status',
            choices=('unpaid', 'paid', 'refunded')
            readonly=True,
        )

    def can_refund(self):
        return True

    @transition(src='paid', dest='refunded', conditions=[can_refund])
    def refund(self):
        return

in views.py

.. code-block:: python

    def refund(request, id):
        if request.method == 'POST':
            order = Order(pk=id)
            order.refund()

DJango Signals
--------------

Sends a 'transition' signal
#TODO

Detailed Examples
-----------------

#TODO