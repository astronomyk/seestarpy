![SeeStar-Py](docs/_static/seestar_py_logo_banner.png)
A light-weight python module to drive the Seestar smart telescopes

This package is on ReadTheDocs. See [seestarpy.readthedocs.io](https://seestarpy.readthedocs.io/en/latest/)


Quickstart
----------
Install `seestarpy` using pip:

    $ pip install seestarpy

Usage example:

    from seestarpy import connection as conn
    from seestarpy import raw

    conn.DEFAULT_IP = "192.168.1.243"
    raw.test_connection()



