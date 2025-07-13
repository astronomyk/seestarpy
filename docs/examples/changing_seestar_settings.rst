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