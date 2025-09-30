Some notes on setting the Seestar gain values
=============================================

High vs Low Conversion Gain modes (HCG vs LCG)

.. code-block::python

    from seestarpy import raw
    raw.set_control_value(gain=80):


According to the docs on the IMX462 chip, it has two internal capacitors
which are used to read the pixel values. The larger capacitor used in the
LCG mode can map the full pixel well depth of 32k electrons, albeit still
only with the 12-bit ADC.
The smaller, more sensitive capacitor used for the HCG mode, can only map
to about a third of the full well depth. However this small capacitor
produces less noise and is therefore much better suited for low-flux objects
such as nebula and galaxies.

Use cases:

- If you prefer to map the full dynamic range of as many stars in the field as
  possible, without the bright ones "burning out" (i.e. saturating) then it
  makes sense to use the LCG mode, with gains set to below 80

- If you are looking for the best possible contrast within extended sources
  like nebulae and galaxy disks, then the HCG mode is better suited. Set the
  gain value to 80+

