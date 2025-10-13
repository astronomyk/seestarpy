[app]
title = Seestar Controller
package.name = seestarcontroller
package.domain = org.seestarpy
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1

# Requirements - we'll handle seestarpy separately
requirements = python3,kivy==2.2.1,requests

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE
android.api = 31
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
