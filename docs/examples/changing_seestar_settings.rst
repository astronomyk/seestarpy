Changing the Seestar's settings
===============================

.. note::
    **Assumption**: That you have already set up a connection to the seestar.
    If not, see :doc:`basic_connection`.


Time and location
-----------------

Check if your Seestar has the right time and place:

.. code-block:: python

    raw.pi_get_time()
    raw.get_user_location()

If the returned values indicate that you are Marty McFly and have landed back in
the year your parents were courting, you may want to run the following:

.. code-block:: python

    raw.pi_set_time()
    # For Vienna, Austria
    raw.set_user_location(48.2, 16.4)

