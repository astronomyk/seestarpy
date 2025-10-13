Sniffing port 4700 for JSON packets
===================================

Prerequisites
-------------
- Download PCAPdroid on to your phone
- Download Wireshark on to your computer

There's a very specific order you have to do things in order to get a good capture:

1) Make sure Seestar is off
2) Force close Seestar app in Settings -> App
3) Start PCapDroid and initiate the packet capture
4) Launch the Seestar App
5) Acknowledge VPN may not work
6) Power on Seestar
7) Run the actions you want to caption traffic for
8) Stop the PCapDroid recording
9) Export the .pcap file to your computer
10) Open the .pcap file with Wireshark, or any other tool of choice

Tips from the Gurus on Discord
------------------------------
Run PCAPDroid on my phone and tell it to monitor all traffic from the Seestar app.
Works reasonably well.
Then use tcpdump afterwards to filter out the traffic I want from the capture file.::

    tcpdump -r PCAPdroid_18_May_14_42_52.pcap -A "tcp port 4700" |grep -o '{.*}' >json.txt

I try to limit my capture sessions to just the commands I want to figure out to limit the size and the amount of data it returns.