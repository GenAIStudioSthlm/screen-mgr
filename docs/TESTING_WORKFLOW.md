# Testing Workflow for News Flow Feature

**Branch:** `staging/news-flow-feature`
**Architecture:** Single Raspberry Pi controlling all screens

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    RASPBERRY PI                         │
│                   (single device)                       │
│                                                         │
│   ┌─────────────┐                                       │
│   │ screen-mgr  │ ◄── FastAPI server on port 8000      │
│   │   (main)    │                                       │
│   └──────┬──────┘                                       │
│          │                                              │
│          ▼                                              │
│   ┌──────────────────────────────────────────────┐     │
│   │           Browser Windows (Chromium)          │     │
│   │  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐  │     │
│   │  │ S1 │ │ S2 │ │ S3 │ │ S4 │ │ S5 │ │ S6 │  │     │
│   │  └────┘ └────┘ └────┘ └────┘ └────┘ └────┘  │     │
│   └──────────────────────────────────────────────┘     │
│          │                                              │
└──────────┼──────────────────────────────────────────────┘
           │
           ▼
    ┌──────────────────────────────────────────────┐
    │              PHYSICAL SCREENS                 │
    │   [Screen1] [Screen2] [Screen3] ...          │
    └──────────────────────────────────────────────┘
```

---

## Testing Phases

### Phase 1: Development (On Development PC)

**Location:** Your development machine (not the Pi)
**Duration:** As long as needed
**Impact:** Zero - production unchanged

```bash
# Clone and setup
git clone <repo-url> screen-mgr-dev
cd screen-mgr-dev
git checkout staging/news-flow-feature

# Setup environment
python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate (Windows)
pip install -r requirements.txt

# Run locally
uvicorn main:app --reload

# Open http://localhost:8000 in browser
# Test screens by opening multiple tabs:
#   http://localhost:8000/screen/1
#   http://localhost:8000/screen/2
#   etc.
```

**What to test:**
- [ ] All new routes respond correctly
- [ ] News admin UI renders properly
- [ ] Article fetching works
- [ ] All three display modes render correctly
- [ ] WebSocket connections work
- [ ] Data persists to JSON files

---

### Phase 2: Integration Testing (On Development PC)

**Duration:** 1-2 sessions
**Impact:** Zero

```bash
# Continue on development PC
# Test with multiple browser windows simulating screens
```

**What to test:**
- [ ] WebSocket reload messages trigger screen refresh
- [ ] Admin panel updates reflect on "screens" (browser tabs)
- [ ] Presentation mode controls work (pause, next, prev)
- [ ] Portrait/landscape/presentation all display correctly
- [ ] Article rotation timing works
- [ ] QR code toggle works

---

### Phase 3: Pi Environment Verification (On Raspberry Pi)

**Location:** Raspberry Pi
**Duration:** 1 session
**Impact:** Minimal - runs on different port

```bash
# SSH into Raspberry Pi
ssh pi@<pi-ip-address>

# Create staging directory (separate from production)
cd /home/pi
git clone /home/pi/screen-mgr screen-mgr-staging
# Or: git clone <repo-url> screen-mgr-staging

cd screen-mgr-staging
git checkout staging/news-flow-feature

# Setup environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run on different port (production stays on 8000)
uvicorn main:app --host 0.0.0.0 --port 8001
```

**Access staging:** `http://<pi-ip>:8001`

**What to test:**
- [ ] App starts without errors on Pi
- [ ] No missing dependencies
- [ ] Performance acceptable on Pi hardware
- [ ] All routes accessible

**Note:** Physical screens won't show this - browser testing only.

---

### Phase 4: Stakeholder Demo (Full Switchover)

**Location:** Raspberry Pi
**Duration:** Scheduled window (coordinate with stakeholders)
**Impact:** ALL SCREENS will show staging version

#### Before the Demo

```bash
# SSH into Raspberry Pi
ssh pi@<pi-ip-address>
cd /home/pi/screen-mgr

# 1. Backup current state
cp screens.json screens.json.prod-backup
git stash  # Save any uncommitted changes

# 2. Note current branch
git branch --show-current
# Should show: main (or whatever production branch is)
```

#### Switch to Staging

```bash
# 3. Fetch and switch to staging branch
git fetch origin staging/news-flow-feature
git checkout staging/news-flow-feature

# 4. Install any new dependencies
pip install -r requirements.txt

# 5. Restart the service
# If using systemd:
sudo systemctl restart screen-mgr

# If running manually, stop current process and:
uvicorn main:app --host 0.0.0.0 --port 8000
```

**All screens now show staging version!**

#### During the Demo

- Show stakeholders the news feature on real screens
- Test all three display modes on physical displays
- Gather feedback
- Note any issues

#### After the Demo - Restore Production

```bash
# 6. Switch back to production
git checkout main
git stash pop  # Restore any stashed changes

# 7. Restore screen configuration
cp screens.json.prod-backup screens.json

# 8. Restart service
sudo systemctl restart screen-mgr
# Or restart uvicorn manually
```

**All screens now back to production!**

---

### Phase 5: Final Deployment

**When:** After stakeholder approval
**Impact:** Permanent change to production

```bash
# On Raspberry Pi
cd /home/pi/screen-mgr

# 1. Backup
cp screens.json screens.json.pre-newsflow-backup

# 2. Merge staging to main
git checkout main
git merge staging/news-flow-feature

# 3. Install dependencies
pip install -r requirements.txt

# 4. Restart
sudo systemctl restart screen-mgr

# 5. Verify
# Check all screens display correctly
# Test news feature on at least one screen
```

---

## Quick Reference Scripts

### Create: `/home/pi/switch-to-staging.sh`

```bash
#!/bin/bash
set -e
echo "Switching to staging..."
cd /home/pi/screen-mgr
cp screens.json screens.json.prod-backup
git stash
git fetch origin staging/news-flow-feature
git checkout staging/news-flow-feature
pip install -r requirements.txt
sudo systemctl restart screen-mgr
echo "Now running STAGING version"
```

### Create: `/home/pi/restore-production.sh`

```bash
#!/bin/bash
set -e
echo "Restoring production..."
cd /home/pi/screen-mgr
git checkout main
git stash pop || true
cp screens.json.prod-backup screens.json
sudo systemctl restart screen-mgr
echo "Now running PRODUCTION version"
```

### Usage

```bash
# Make executable
chmod +x /home/pi/switch-to-staging.sh
chmod +x /home/pi/restore-production.sh

# Switch to staging for demo
./switch-to-staging.sh

# Restore production after demo
./restore-production.sh
```

---

## Rollback Plan

If something goes wrong at any point:

```bash
# Emergency rollback
cd /home/pi/screen-mgr
git checkout main
cp screens.json.prod-backup screens.json
sudo systemctl restart screen-mgr
```

---

## Checklist for Stakeholder Demo

**Before:**
- [ ] Notify stakeholders of demo time
- [ ] Backup `screens.json`
- [ ] Note current git branch
- [ ] Prepare rollback script

**During:**
- [ ] Switch to staging branch
- [ ] Verify all screens are working
- [ ] Demo news feature
- [ ] Collect feedback

**After:**
- [ ] Restore production branch
- [ ] Restore `screens.json`
- [ ] Verify all screens working normally
- [ ] Document feedback and issues
