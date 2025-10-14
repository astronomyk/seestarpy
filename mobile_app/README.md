Run the SeestarPy App
=====================

Currently, this only runs locally on a machine that has a copy of the SeestarPy
repo. The idea is to use Kivy and Buildozer to create an android APK out of it.
However, the Buildozer toolchain is a piece of sh**.

Anyway, for now, this works as follows:

    $ cd path/to/repo/seestarpy
    $ cd ./mobile_app
    $ python main_chatgpt.py

This should give you a very minimalistic single screen control app for Seestarpy

You may need to install Kivy if this doesn't kick off straight away

    $ pip install kivy