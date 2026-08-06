Installing on a Raspberry Pi Zero W
===================================

.. note::
   **Prerequisites:**

   - A Raspberry Pi Zero W (or any ``armv6l`` board) with Raspberry Pi OS /
     Raspbian and network access.
   - `uv <https://docs.astral.sh/uv/>`_ installed (``curl -LsSf
     https://astral.sh/uv/install.sh | sh``), or plain ``pip``.
   - The RSA signing key from a machine that has already been paired with
     your Seestar (see :doc:`../info/authentication`).

The Raspberry Pi Zero W is a popular host for unattended, headless jobs —
for example a service that stacks and uploads the night's observations once
observing has finished.  Its ARMv6 CPU needs one extra step during install,
described below.


The ARMv6 wheel problem
-----------------------

On a 64-bit PC or a Raspberry Pi 3/4/5, ``pip install seestarpy`` /
``uv add seestarpy`` just works.  On a **Pi Zero / Zero W / 1** it does not,
because those boards use the ``armv6l`` architecture and **PyPI ships no
prebuilt wheels for ARMv6**.  seestarpy depends on ``cryptography`` (for the
firmware 7.18+ RSA handshake), which in turn depends on ``cffi``, and pip is
forced to compile both from source.  That fails: ``cffi`` needs
``python3-dev`` / ``libffi-dev``, and ``cryptography`` needs a Rust toolchain
plus enough RAM to run it — which a 512 MB single-core board does not have.


The fix: install from piwheels
-------------------------------

`piwheels <https://www.piwheels.org>`_ is a service that hosts prebuilt ARM
wheels for the whole of PyPI, including ``cryptography`` and ``cffi``.  Using
it, the install needs **no compilation at all**.

With ``uv``
~~~~~~~~~~~

``uv`` stops at the first index that has a match by default, so it would grab
PyPI's source distribution and never look at piwheels.  Pass
``--index-strategy unsafe-best-match`` so it considers the piwheels wheel:

.. code-block:: bash

   uv add seestarpy \
     --extra-index-url https://www.piwheels.org/simple \
     --index-strategy unsafe-best-match

To make this reproducible (``--extra-index-url`` is not saved to
``pyproject.toml``), pin the index in your project's ``pyproject.toml`` so
future ``uv sync`` / ``uv lock`` calls keep using piwheels:

.. code-block:: toml

   [tool.uv]
   index-strategy = "unsafe-best-match"

   [[tool.uv.index]]
   name = "piwheels"
   url = "https://www.piwheels.org/simple"

With ``pip``
~~~~~~~~~~~~

On Raspberry Pi OS, ``pip`` is usually already configured to use piwheels via
``/etc/pip.conf``.  If not, add the index explicitly:

.. code-block:: bash

   pip install seestarpy --extra-index-url https://www.piwheels.org/simple

.. note::
   piwheels wheels are tagged for the Raspberry Pi OS system Python (e.g.
   Python 3.13 on Raspberry Pi OS *trixie*).  If you later upgrade the OS
   Python major/minor version, re-run the install / ``uv lock`` so it picks
   matching wheels.


Verifying the install
----------------------

.. code-block:: bash

   python -c "import seestarpy, cryptography; print('ok', cryptography.__version__)"


Copying over the RSA signing key
--------------------------------

Seestar firmware 7.18+ requires a signed RSA challenge-response handshake on
every connection (see :doc:`../info/authentication` for the full story).  The
Pi needs the **same private key** that your paired machine already uses.  It
cannot be regenerated on the Pi — copy it across.

seestarpy looks for the key in this order, using the first that exists:

#. the file named by the ``SEESTAR_KEY_PATH`` environment variable,
#. ``./seestar.pem`` in the current working directory,
#. ``~/.seestarpy/seestar.pem`` — the recommended default.

On the machine that already has the key (its default location is
``~/.seestarpy/seestar.pem``), copy it to the Pi with ``scp``.  Replace
``pi@raspberrypi.local`` with your Pi's user and host:

.. code-block:: bash

   # on the Pi: create the directory with tight permissions
   ssh pi@raspberrypi.local "mkdir -p ~/.seestarpy && chmod 700 ~/.seestarpy"

   # from the source machine: copy the key over
   scp ~/.seestarpy/seestar.pem pi@raspberrypi.local:~/.seestarpy/seestar.pem

   # on the Pi: lock the key down to owner-only
   ssh pi@raspberrypi.local "chmod 600 ~/.seestarpy/seestar.pem"

On Windows, use ``pscp`` (bundled with PuTTY) in place of ``scp``, and copy
from ``%USERPROFILE%\.seestarpy\seestar.pem``.

Confirm seestarpy discovers it:

.. code-block:: bash

   python -c "from seestarpy import auth; print(auth.KEY_PATH)"
   # -> /home/pi/.seestarpy/seestar.pem

.. warning::
   The ``.pem`` file is a **secret**.  Keep it at mode ``600``, never commit
   it to version control, and do not share it.

That's it — seestarpy is installed and can authenticate.  From here you can
connect (:doc:`basic_connection`) or run the automated stacking workflow
(:doc:`crowdsky_stacking`).
