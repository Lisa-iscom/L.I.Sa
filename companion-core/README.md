# Companion Core — Lisa's Brain

Local AI companion. Runs on your hardware. Remembers you. No cloud.
Model   : Qwen2.5-7B or 3B (auto-selected by RAM)
Engine  : llama.cpp
OS      : Ubuntu 22.04 / Debian 12
Access  : http://LOCAL_IP:7777
## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/lisa.git
cd lisa/companion-core

bash install.sh
# Then edit config.yaml — change the password
bash run.sh
Open in browser: http://YOUR-PC-IP:7777
How memory works
Every conversation, Lisa:
Reads SOUL.md + facts.json + relationship.md as context
Saves the last 20 messages to dialogue.json
Runs a background analysis to extract new facts about you
Updates her memory files automatically
She gets to know you over time.
Hardware requirements

Minimum
Recommended
CPU
4 cores
Ryzen 7840
RAM
8 GB
16 GB
Disk
10 GB
SSD 20 GB+
OS
Ubuntu 20.04+
Ubuntu 22.04
Troubleshooting
Server won't start:
ls -lh models/
Slow responses:
Reduce context_size to 4096 in config.yaml
Can't open from another device:
sudo ufw allow 7777
