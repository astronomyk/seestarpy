Event Error Messages
====================

====  =============================  =================================
Code  Error Message                  Events
====  =============================  =================================
0     no error                       Stack
203   equipment is moving            ScopeTrack
207   fail to operate                ScopeTrack
251   solve failed                   AutoGoto, PlateSolve
263   stack error, too few stars     Alert, Stack
264   stack error, transform failed  Alert
270   below horizon                  Alert, ScopeTrack
279   no star is detected            AutoFocus
501   mount goto failed              AutoGoto, AutoGotoStep, ScopeGoto
502   mount sync failed              ScopeTrack
514   interrupt                      Exposure
530   star trails                    Alert, Stack
====  =============================  =================================


Command reply codes
===================

Codes returned in the ``code`` field of a JSON-RPC reply on port 4700.

====  =============================  ===========================================
Code  Error Message                  Typical cause
====  =============================  ===========================================
103   method not found               Method not supported by this firmware
104   invalid track params           ``start_track_object`` (firmware 9.x)
105   expected string param          Wrong parameter type
207   fail to operate                No data yet, e.g. photometry before a frame
209   invalid track rect             ``start_track_object`` ROI (firmware 9.x)
267   no image                       ``get_photometry_wcs`` without a frame
268   operation is in progress       Another view/plan is running
====  =============================  ===========================================
