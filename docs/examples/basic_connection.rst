Basic Connection to your Seestar
================================

.. note::
    **Assumptions:**
    These assumptions apply to the ``seestarpy`` use case:

    - You are happy with ``python`` and like to use scripts and/or python notebooks
    - You have already set your Seestar to station mode and it connects happily to
      your local wifi network or phone hotspot

First things first - tell seestarpy your IP address. This can be found in the
seestar phone app under the advanced settings where you set up station mode.

.. code-block:: python

    from seestarpy import connection as conn
    from seestarpy import raw

    # replace this with the IP of your Seestar
    conn.DEFAULT_IP = "192.168.1.243"
    raw.test_connection()

This should allow you to see whether the have right IP address for the seestar.

.. todo:: Add code that automatically finds a Seestar on the network

Now raise the seestar arm and point it somewhere:

.. code-block:: python

    raw.scope_move_to_horizon()
    raw.goto_target()