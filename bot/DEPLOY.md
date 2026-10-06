# Running the Testnet bot on cPanel hosting (cron job)

The bot runs once a week for a few seconds; it needs a scheduled task, not a website.
Requirements: cPanel with **Setup Python App** (Python **3.10 or newer**) and **Cron Jobs**.

1. **Get the code** — cPanel → *Git Version Control* → *Create* → clone
   `https://github.com/nidhalom/sandbox-research` into e.g. `/home/USER/sandbox-research`.
2. **Python environment** — cPanel → *Setup Python App* → *Create Application*: Python 3.10+ (3.11/3.12
   preferred), *Application root* `sandbox-research`, no domain needed. Open the app, add
   `requirements-bot.txt` under *Configuration files*, click *Run Pip Install*. Note the
   "Enter to the virtual environment" command it shows, e.g.
   `source /home/USER/virtualenv/sandbox-research/3.11/bin/activate`.
3. **Keys** — cPanel → *File Manager* → in `sandbox-research/` create `.env` with
   `BINANCE_TESTNET_KEY=...` and `BINANCE_TESTNET_SECRET=...`, then *Permissions* → `600`.
   Testnet keys only.
4. **Carry over the running test** — upload `bot/state-fixed-CASH.json`, `bot/fills-fixed-CASH.csv` and
   `bot/runs-fixed-CASH.csv` from the PC into `sandbox-research/bot/`. **Stop running it on the PC**:
   two copies would trade twice.
5. **Test** (cPanel → *Terminal*, after the activate command):
   `cd ~/sandbox-research && python -m bot.testnet --check` then `python -m bot.testnet --strategy fixed --gold CASH`
   (dry run: must show the same holdings as on the PC).
6. **Cron job** — cPanel → *Cron Jobs*, every Tuesday at 00:10 **UTC**. Check the server's time zone
   first (`date` in Terminal); if it is UTC+1, use 01:10. Command:

   ```
   cd /home/USER/sandbox-research && /home/USER/virtualenv/sandbox-research/3.11/bin/python -m bot.testnet --live --strategy fixed --gold CASH >> /home/USER/sandbox-research/bot/cron.log 2>&1
   ```
7. **Updates** — *Git Version Control* → *Pull*. `.env`, state and logs are gitignored, so pulls never touch them.
