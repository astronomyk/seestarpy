Authentication (Firmware 7.18+)
===============================

Starting with firmware version 7.18, ZWO added a mandatory
challenge-response handshake to the Seestar's JSON-RPC interface
(port 4700).  Third-party software must complete this handshake before
the telescope will accept any commands.

seestarpy handles this transparently via the :mod:`~seestarpy.auth`
module --- once you place the key file in the right location, every
connection authenticates automatically.


How the handshake works
-----------------------

The authentication is a 3-step RSA challenge-response exchange that
happens immediately after a TCP connection is established:

1. **Challenge request** --- seestarpy sends ``get_verify_str`` to the
   telescope.  The telescope replies with a random string (the
   "challenge").

2. **Signature** --- seestarpy signs the challenge with an RSA private
   key using SHA-1 (PKCS#1 v1.5), base64-encodes the result, and sends
   it back via ``verify_client``.  This proves possession of the correct
   key without transmitting it.

3. **Confirmation** --- seestarpy sends ``pi_is_verified`` as a final
   acknowledgement.  The telescope responds, and authentication is
   complete.

All three steps happen behind the scenes.  Your code simply calls
``raw.test_connection()`` (or any other command) and it works.

.. note::

   On older firmware (< 7.18), the telescope does not recognise the
   ``get_verify_str`` method and returns error code 103.  seestarpy
   detects this and skips authentication, so the same code works on
   both old and new firmware.


Setup
-----

You need two things:

1. **The ``cryptography`` library** (or ``openssl`` on PATH)::

      pip install seestarpy[auth]

   If ``cryptography`` is not installed, seestarpy falls back to
   shelling out to the ``openssl`` command-line tool.

2. **The RSA private key** in PEM format.  seestarpy ships with a
   built-in extractor that pulls the key out of a Seestar APK you
   have obtained.

Extracting the key from an APK
------------------------------

Obtain the official ZWO Seestar Android APK yourself (for example
from an APK mirror site such as APKPure), then run::

   python -m seestarpy.extract_pem /path/to/Seestar_v3.1.2.apk

On success the key is written to ``~/.seestarpy/seestar.pem``, which
is one of the locations seestarpy auto-discovers on every connection.

Useful flags:

- ``-o PATH`` --- write to a custom location.
- ``--stdout`` --- print the key(s) to stdout instead of writing a
  file.  Handy if the APK contains multiple keys.
- ``-q`` --- suppress progress messages.

The extractor is a generic utility: it opens the APK as a ZIP,
reads the native library ``lib/arm64-v8a/libopenssllib.so`` (or the
``armeabi-v7a`` variant), runs a ``strings(1)``-style scan, and
matches any ``-----BEGIN PRIVATE KEY-----`` block it finds.  It has
no ZWO-specific logic and ships no key of its own.


Key auto-discovery
------------------

seestarpy searches for the key in this order:

1. The ``SEESTAR_KEY_PATH`` environment variable (if set and the file
   exists).
2. ``seestar.pem`` in the current working directory.
3. ``~/.seestarpy/seestar.pem`` (i.e. a ``.seestarpy`` folder in your
   home directory) --- this is where the extractor writes by default.

On Windows, ``~/.seestarpy/`` resolves to
``C:\Users\<you>\.seestarpy\``.

You can also set the path at runtime::

   from seestarpy import auth
   auth.set_key_path("/path/to/seestar.pem")


Verifying it works
------------------

.. code-block:: python

   from seestarpy import auth, raw

   # Confirm the key was found
   print(auth.KEY_PATH)       # Should print a path, not None

   # Test the connection (auth happens automatically)
   result = raw.test_connection()
   print(result["code"])      # 0 = success

If ``auth.KEY_PATH`` is ``None``, the key was not found in any of the
three auto-discovery locations.


About the RSA key
-----------------

The key is **not unique per device or per user**. Every copy of the app
contains the same key, and it has remained identical across APK versions
(verified with v3.0.2 and v3.1.2).

The telescope's firmware holds the corresponding public key and uses it
to verify signatures during the handshake.  Because the private key is a
single global key, the handshake only proves that the connecting software
has access to the same key as the official app --- it does not identify
individual users or devices.


Legal considerations
--------------------

.. note::

   This section provides general information about the legal landscape.
   It is **not legal advice**.  Consult a qualified attorney if you have
   specific concerns.


United States --- DMCA
^^^^^^^^^^^^^^^^^^^^^^

Section 1201(a) of the Digital Millennium Copyright Act (DMCA) prohibits
circumventing "technological measures that effectively control access to
a copyrighted work."  At first glance, bypassing the handshake might
seem to trigger this provision.  However, several factors weigh against
that reading:

**Nexus requirement.**
The DMCA requires a link between the protection measure and a
*copyrighted work*.  The handshake gates access to a functional hardware
interface (sending commands to a telescope you own), not to copyrighted
software or creative content.  In *Chamberlain Group v. Skylink
Technologies* (Fed. Cir. 2004), the court rejected a DMCA claim over
garage-door-opener authentication codes, ruling that bypassing an access
control on a device's functionality is not the same as accessing a
copyrighted work.  *Lexmark v. Static Control Components* (6th Cir.
2004) reached the same conclusion for authentication chips in printer
cartridges.

**Interoperability exception.**
DMCA Section 1201(f) permits reverse engineering "for the sole purpose
of identifying and analyzing those elements of the program that are
necessary to achieve interoperability of an independently created
computer program with other programs."  seestarpy is an independently
created program interoperating with the Seestar's firmware.

**"Effective" threshold.**
The DMCA only protects measures that "effectively control access."
Embedding a private key as unencrypted ASCII text inside a publicly
downloadable APK is, at best, a weak form of access control.  Courts
have been sceptical of calling a protection measure "effective" when
the secret is distributed alongside the product.


European Union --- Software Directive
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The EU's legal framework is generally **more favourable** to
interoperability than the US.

**Software Directive (2009/24/EC), Article 6.**
This provides a mandatory, non-waivable right to reverse-engineer
software for interoperability purposes.  Unlike the DMCA's
interoperability exception, this right:

- Cannot be overridden by contract (EULAs or terms of service that
  prohibit reverse engineering are unenforceable on this point).
- Does not require periodic renewal.
- Explicitly covers decompilation and disassembly.

**Functional interfaces are not copyrightable.**
In *SAS Institute v. World Programming* (CJEU 2012), the Court of
Justice of the European Union ruled that neither the functionality of a
program, nor its programming language, nor the format of its data files
constitutes copyrightable expression.  A JSON-RPC authentication
protocol is a functional interface.

**Anti-circumvention (Copyright Directive 2001/29/EC, Article 6).**
The EU has its own anti-circumvention provisions, but member states must
ensure that they do not override the Software Directive's
interoperability exception.

**Regulatory trend.**
Recent EU legislation --- the Cyber Resilience Act (2024) and the Right
to Repair Directive (2024/1799) --- reinforces the principle that
consumers have rights to use, maintain, and interoperate with products
they have purchased.


US vs. EU comparison
^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Aspect
     - US (DMCA)
     - EU (Software Directive)
   * - Interoperability exception
     - Exists (Section 1201(f)), narrower
     - Stronger, non-waivable, explicit
   * - Can EULA override it?
     - Debated, varies by circuit
     - No (Article 6 cannot be contracted away)
   * - Functional interfaces copyrightable?
     - Mostly no (*Oracle v. Google*)
     - No (*SAS v. WPL*)
   * - Needs periodic renewal?
     - Some exemptions do
     - No --- permanent statutory right
   * - Regulatory direction
     - Mixed
     - Strongly pro-consumer / interoperability


What seestarpy does and does not include
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- seestarpy **does not** bundle the RSA private key.  Users extract it
  themselves from an APK they have obtained.
- seestarpy **does not** distribute ZWO's proprietary software, firmware,
  or APK files.
- The ``extract_pem.py`` tool (in a separate repository) documents an
  extraction technique and is analogous to other widely used reverse
  engineering tools.
- The purpose is interoperability with hardware the user owns.
