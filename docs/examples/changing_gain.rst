Setting the gain
================

Gain is how much the camera amplifies the signal before it is digitised.
It does not collect more light — it changes how the light that *was*
collected is mapped onto the 12-bit numbers that end up in your FITS file.
On the Seestar it is the one exposure control with a genuine
either/or decision behind it, because the sensor switches hardware
behaviour at gain 80.

.. code-block:: python

   from seestarpy import raw

   raw.set_control_value(gain=80)

Gain is applied to the **live view and to subsequent subs**, so set it
before you start stacking.  Like everything else, it accepts ``ips=``:

.. code-block:: python

   raw.set_control_value(gain=60, ips="all")

To read back what the scope is currently using:

.. code-block:: python

   from seestarpy import raw, status

   raw.iscope_get_app_state()["result"]["View"].get("gain")

   # or just look at the GAIN cell of the dashboard
   print(status.status_bar())

The live gain lives on the ``View`` block, which means it only has a value
once a view is running.  Before that the field is absent — an idle scope
has no gain to report.


HCG vs LCG: why 80 is the magic number
--------------------------------------

The S50's IMX462 sensor has **two internal capacitors** for reading pixel
values, and the driver picks between them based on the gain you ask for:

**LCG — Low Conversion Gain (gain < 80).**  The larger capacitor.  It can
map the full pixel well depth of ~32k electrons, albeit still only through
the 12-bit ADC.  More headroom before a pixel saturates.

**HCG — High Conversion Gain (gain ≥ 80).**  The smaller, more sensitive
capacitor.  It reaches only about a third of the full well depth, but it
produces measurably less read noise — which is what dominates when each
sub is only 10–30 s of a faint target.

So the choice is well depth versus read noise:

- **Use LCG (gain 30–60)** when you want to map the dynamic range of as
  many stars in the field as possible without the bright ones burning out.
  Open clusters, bright doubles, anything where saturated cores would ruin
  the point, and any photometry where you need bright stars to stay linear.

- **Use HCG (gain 80+)** when you are after the best possible contrast in
  extended, low-surface-brightness structure — nebula filaments, galaxy
  disks and outer arms, integrated flux nebulae.  Bright stars will
  saturate; that is the trade you are making.

Crossing 80 is a *discontinuity*, not a smooth ramp.  Gain 79 and gain 80
are not one step apart in noise behaviour — they are two different readout
paths.  Do not compare or mix subs taken either side of the boundary
within one stack.

.. note::
   Raising gain does **not** reduce the noise in your final image in any
   absolute sense; it reduces the *read noise contribution per sub*.  Total
   integration time is still what buys signal-to-noise.  If your subs are
   already long enough that sky background dominates read noise, the gain
   choice matters much less than how long you keep observing.


Picking a gain in practice
--------------------------

If you are unsure, gain 80 is a sensible default for deep-sky work — it is
the firmware's own default, and it sits at the bottom of the HCG range,
which gives you the low-noise readout path without amplifying more than
necessary.

For a target with a big brightness range (say M42, whose core saturates
long before the outer nebulosity shows up), the useful trick is to take
two sets and combine them later:

.. code-block:: python

   import seestarpy as ssp
   from seestarpy import raw

   ssp.goto_target("M42")

   # Deep pass: HCG, faint structure
   raw.set_control_value(gain=80)
   ssp.exposure(20)
   ssp.start_stack()
   ...                                  # let it run

   # Short pass for the unsaturated core: LCG, short subs
   ssp.stop_view()
   raw.set_control_value(gain=30)
   ssp.exposure(5)
   ssp.goto_target("M42 core")          # separate folder = separate stack
   ssp.start_stack()

Keeping them in separate target folders matters: the folder name is the
stack, and you do not want the firmware averaging two different readout
modes together.  See :doc:`data_management` for getting the frames off the
scope afterwards.
