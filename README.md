# TikTok Daily Streak Automation (`playwright` Async)

A modular Python automation tool that maintains your daily TikTok streaks on [TikTok Web Messages](https://www.tiktok.com/messages) (both active/flaming `🔥` streaks and unlit/"not flaming up" gray streaks) using a persistent Chromium profile, human-like typing delays, and a daily JSON lockfile (`streak_log.json`).

---

## Project Structure

- [main.py](file:///C:/Users/Kier/Documents/tiktok-streak-bot/main.py) — Core async Playwright script supporting `--login`, `--export-session`, `--dry-run`, `--debug-dom`, and `--headless`.
- [config.py](file:///C:/Users/Kier/Documents/tiktok-streak-bot/config.py) — Customizable message pool (`MESSAGES_POOL`), human delay ranges, `INCLUDE_UNLIT_STREAKS`, `STREAK_LOOKBACK_DAYS`, `FALLBACK_STREAK_USERS`, and DOM selectors.
- [setup_scheduler.ps1](file:///C:/Users/Kier/Documents/tiktok-streak-bot/setup_scheduler.ps1) — Registers the `TikTokDailyStreakBot` task in Windows Task Scheduler (runs daily at 9:00 AM and 8:00 PM with wake & catch-up enabled).
- [.github/workflows/daily_streak.yml](file:///C:/Users/Kier/Documents/tiktok-streak-bot/.github/workflows/daily_streak.yml) — Free 24/7 cloud workflow (GitHub Actions) that sends your streak messages even when your PC and phone are completely turned **OFF**.
- [streak_log.json](file:///C:/Users/Kier/Documents/tiktok-streak-bot/streak_log.json) — Daily lockfile recording which chats have already been messaged on the current `YYYY-MM-DD`.

---

## Running While You Are Away (No PC or Phone Access Needed)

### Mode 1: PC Left On or Asleep (Already Active on Your PC)
The Windows Scheduled Task **`TikTokDailyStreakBot`** is already registered on your PC via [setup_scheduler.ps1](file:///C:/Users/Kier/Documents/tiktok-streak-bot/setup_scheduler.ps1):
- Runs `main.py --headless` automatically in the background at **9:00 AM** and **8:00 PM** every day.
- Configured with **`WakeToRun`** (wakes your PC from sleep) and **`StartWhenAvailable`** (runs immediately the moment your PC wakes up if a scheduled time was missed).
- Logs all activity to `streak_automation.log`.

### Mode 2: PC & Phone Completely Turned OFF (24/7 Cloud via GitHub Actions — 100% Free)
If your PC will be completely powered off or unplugged while you are away:
1. Create a **Private** repository on GitHub and push this folder (`C:\Users\Kier\Documents\tiktok-streak-bot`) to it (`.gitignore` automatically protects `tiktok_profile/` and `storage_state.json` from being uploaded).
2. Open your exported [storage_state.json](file:///C:/Users/Kier/Documents/tiktok-streak-bot/storage_state.json) file and copy its entire JSON contents.
3. In your private GitHub repository, go to **Settings → Secrets and variables → Actions → New repository secret**:
   - **Name:** `TIKTOK_STORAGE_STATE`
   - **Secret:** Paste the entire contents of `storage_state.json`.
4. GitHub's cloud servers will automatically run [.github/workflows/daily_streak.yml](file:///C:/Users/Kier/Documents/tiktok-streak-bot/.github/workflows/daily_streak.yml) twice a day (`9:00 AM` and `8:00 PM` PHT) and update `streak_log.json`, even when your PC and phone are both powered off.
