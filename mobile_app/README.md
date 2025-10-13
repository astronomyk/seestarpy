For Future Sessions
Every time you open WSL and want to build, you'll need to activate the environment:
bashcd /mnt/e/WHOPA/seestarpy
source mobile_env/bin/activate
Tip: You can add an alias to your ~/.bashrc to make this easier:
bashecho "alias seestar='cd /mnt/e/WHOPA/seestarpy && source mobile_env/bin/activate'" >> ~/.bashrc
source ~/.bashrc
Then you can just type seestar to jump to your project with the venv activated!