Events Module
=============

The events subsystem provides a real-time stream of Seestar state
changes over a persistent TCP connection.  Use
:func:`~seestarpy.events.event_listener.start_listener` to begin
collecting events in a background thread, and inspect
:data:`~seestarpy.events.event_stream.LATEST_STATE` for the most
recent data.

Listener
--------

.. automodule:: seestarpy.events.event_listener
    :members:
    :undoc-members:
    :show-inheritance:

Event Stream
------------

.. automodule:: seestarpy.events.event_stream
    :members:
    :undoc-members:
    :show-inheritance:
