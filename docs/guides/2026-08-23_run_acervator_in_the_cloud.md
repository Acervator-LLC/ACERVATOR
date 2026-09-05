# Run Acervator in the cloud with its window visible

This is a How-to guide. It also explains the reasons for each step, so
you can judge the advice instead of only obeying it.

You asked for two things. You want Acervator to run in the cloud, on
Linux. You want to see the full window wherever it runs. This document
tells you how to do that. It also tells you the one thing that can lose
you money, and how to prevent it.

Every claim below carries a mark. **[TREE]** means I measured it in
your own code. **[WEB]** means I read it on the internet and could not test it
here. **[UNKNOWN]** means I could not establish it at all.

---

## Read this first: two copies must never trade one account

Your Coinbase account holds one set of coins. Acervator decides what to
do by comparing what it believes it owns against what the exchange
reports. If two copies of Acervator connect to the same Coinbase
account, each copy sees the other copy's trades as coins that appeared
or vanished for no reason. Each copy then corrects for a change it did
not make. The two copies fight each other, and each correction costs
you a fee and a bad price.

This is not a distant risk. I am told it is the same condition as the
Target Delta defect repaired on 2026-08-22, made continuous instead of
momentary. I did not re-verify that repair for this document, so treat
the link to it as reported rather than measured.

The rule is therefore simple, and it comes before every other
instruction in this guide:

> **Exactly one copy of Acervator may hold your live Coinbase keys and
> run bots at any moment. Before you start the cloud copy, you must stop
> the desktop copy.**

### How fast the danger arrives

You cannot start a cloud copy "just to look at it". [TREE]

At startup, `main.py:970` reads the saved fleet. `main.py:1005` counts
every bot in the `idle` or `stopped` state. `main.py:1437-1457` then
starts every one of those bots about 9.25 seconds after launch. No
setting controls this. No prompt appears. No flag turns it off.

If you copy your `~/.acervator/` folder to a cloud machine and launch
the application, that machine begins to trade your real account within
ten seconds.

### The safe way to build and test the cloud machine

A safe path exists, and it also comes from the code. [TREE]

`state_manager.py:573` (`has_saved_state`) returns false when no saved
fleet file exists. With no saved fleet, the application makes no bots, so the
count at `main.py:1005` is zero and nothing auto-starts. The
application also cannot reach Coinbase without stored keys.

**Build the entire cloud machine with an empty `~/.acervator/` folder.**
Do not copy your settings or your fleet across. Confirm that the window
appears, that it is smooth enough to use, and that it survives you
closing your laptop. Only after all of that passes should you decide
whether to move the account across at all.

---

## What guards against a second copy today

The instance guard does. [TREE]

`src/core/instance_guard.py` runs before the saved fleet can auto-start, and
`main.py` calls it on every launch. It does two things. It takes an exclusive
operating-system lock on a file in the state directory and holds that lock for
the life of the process. It also writes a claim file recording which machine
owns that directory. A launch that cannot take the lock, or that reads a claim
naming a different machine, is refused a silent start and is sent to a consent
dialog instead.

```python
VERDICT_FIRST_RUN = "first_run"
VERDICT_SAME_MACHINE = "same_machine"
VERDICT_LIVE_INSTANCE = "live_instance"
VERDICT_FOREIGN_MACHINE = "foreign_machine"
VERDICT_UNCLAIMED_FLEET = "unclaimed_fleet"
VERDICT_UNCERTAIN = "uncertain"

AUTO_START_PERMITTED = frozenset({VERDICT_FIRST_RUN, VERDICT_SAME_MACHINE})
```

Three findings still deserve your attention.

**The guard protects one state directory, not two machines.** Both the lock and
the claim live inside the folder they protect. Your desktop and a cloud machine
have separate disks and separate home folders, so each one reads its own folder,
calls the launch a first run, and starts. The guard stops the second copy only
where the state directory travels with you: copy that folder to the cloud
machine and the claim inside it names your desktop, the machine fingerprints
differ, and the launch refuses to start the fleet on its own.

**The watchdog makes detection worse, not better.** The application writes a
heartbeat file holding a timestamp and a process id, and refreshes it every two
seconds. It never reads that file back as a claim of ownership. The out-of-process
watchdog **deletes** the heartbeat when it starts, on the assumption that any
existing heartbeat is stale, so a second launch erases the first copy's only
sign of life.

**The state files carry no owner.** `bot_state.json` and
`reservation_state.json` have no host name, no machine id, and no lease of their
own. Each write replaces the file. The last writer wins. The claim sits beside
them; it does not travel inside them.

This matches what other trading platforms do. Freqtrade's answer to multiple
instances is to partition the money, not to prevent the second instance. No
framework surveyed prevents it.

### The mechanism you must use instead

Because the instance guard cannot see across two machines, the second
guard has to be a procedure that you perform, and it must be one you
cannot forget.

1. **Move the keys, do not copy them.** Keep one set of live Coinbase
   API keys. When the cloud machine becomes the authority, delete the
   stored keys from the desktop copy through the Settings dialog.
   A copy with no keys cannot trade.
2. **Better: use two API keys and disable one at Coinbase.** Coinbase
   lets you create and delete API keys. Create a second key for the
   cloud machine. Delete the desktop key at Coinbase the moment the
   cloud machine takes over. A deleted key cannot trade even if you
   launch the desktop copy by mistake. This guard sits at the exchange,
   which is the only place both machines must obey.

The second option is stronger, and I recommend it. The first option
depends on your memory. The second does not.

---

## Why the other two shapes are closed

You ruled that you want the full window wherever the application runs.
That closes two options that were on the table, and I record them here
so a later reader knows they were considered.

**A headless trading engine is closed.** It has no window by
definition. It would also be a large piece of work, not a small one:
`main.py:601-651` shows that a Qt timer is the only thing that advances
the trading loop, so removing the window would stop the trading. [TREE]

**Cloud monitoring only is closed.** It would leave the trading on your
desktop and show you a copy of the logs. That answers "see it from
anywhere" but not "run it in the cloud".

---

## What your tree already contains for Linux

You may not know this, but a working Linux deployment already exists in
your own repository, in the `deploy/kiosk/` folder. Its name is AcervatorOS. It
targets Raspberry Pi OS and Debian. It is much closer to the answer than
anything else you have, and the cloud plan should start from it rather
than from nothing. [TREE]

It contains an installer (`deploy/kiosk/install.sh`), an updater
(`deploy/kiosk/update.sh`), an uninstaller, a systemd service unit
(`deploy/kiosk/systemd/acervator.service`), a pre-flight check script, firewall
rules, and display configuration.

`deploy/kiosk/install.sh` already accepts a `--headless` flag. On that path it
installs TigerVNC and writes a VNC startup file. Somebody has already
thought about a machine with no monitor.

### A correction to an earlier claim about the service file

I was told that `ExecStart` in the service unit points at a `main.py`
inside a `src` folder, that no such file exists in your tree, and that
this is a defect. I checked, and **that claim is wrong**. [TREE]

`deploy/kiosk/install.sh:289` copies the whole repository into
`/opt/acervator/src/`. The repository root, which holds `main.py`,
therefore lands at `/opt/acervator/src/`. The unit's
`ExecStart=__VENV_DIR__/bin/python3 __INSTALL_DIR__/src/main.py`
resolves to `/opt/acervator/src/main.py`, which is your repository root
`main.py`. The path is correct. The pre-flight script confirms the same
layout when it refers to `/opt/acervator/src/src/core/usb_auth.py`.

I report this because the guide must not send you to repair something
that works.

### Defect one: the installer stops before it installs the service

This one is real, and it blocks everything. [TREE]

Every line number in this section describes the tree BEFORE the issue
#88/#95 repair, at commit d3cfe99. The repair moved the assignment, so
the numbers no longer point at what they describe.

`deploy/kiosk/install.sh` set `set -euo pipefail` at line 24. The `-u` option
makes the shell exit when it expands a variable that has no value.

The script used `SCRIPT_DIR` at lines 249, 252 and 253. It assigned
`SCRIPT_DIR` at line 260.

I tested the exact shell behaviour rather than assume it. Under
`set -u`, an unset variable ends the script immediately, and a trailing
`|| true` does **not** rescue it. `deploy/kiosk/install.sh` therefore exited at
line 249.

Everything after line 249 never ran. That included the systemd
service, the VNC configuration, the firewall, and the time
synchronisation setup. The installer, as committed at d3cfe99, did not
finish.

**REPAIRED.** Issue #88/#95 moved the `SCRIPT_DIR` assignment to the
top of the file, above every use.
`tests/test_os_installer_suite.py` now fails when ANY variable in the
`deploy/kiosk/` suite appears above its first assignment. That guards the defect
class, and not only this one instance.

### Defect two: the installer demands a Python that Debian does not ship

At commit d3cfe99, `deploy/kiosk/install.sh:163` ran `python3.12 -m venv`, and
line 105 asked apt for a `python3.12` package. The file header names Debian 12, Raspberry Pi OS
Bookworm and Ubuntu 22.04 as targets. [TREE]

Debian 12 ships Python 3.11 and has no `python3.12` package in its
standard repositories. [WEB] Ubuntu 24.04 LTS ships Python 3.12 and does
have that package. [WEB]

The installer therefore worked on Ubuntu 24.04 and failed on two of the
three systems its own header named.

Your `pyproject.toml` asks only for Python 3.11 or later, so the
hard-coded 3.12 was stricter than the application needs. [TREE]

**REPAIRED.** Issue #88/#95 removed the version from the package list.
The installer now asks apt for the unversioned `python3`,
`python3-venv`, `python3-dev` and `python3-pip`, then checks the
interpreter it gets against the floor in `pyproject.toml`. Debian 12
and Raspberry Pi OS Bookworm meet that floor with 3.11. Ubuntu 22.04
ships 3.10 and does not, and the installer now says so and stops
instead of failing further on.

**Ubuntu 24.04 LTS is still the recommendation for a cloud machine.**
It is the newest of the supported targets. The repair means Debian 12
is no longer excluded.

### Defect three: the firewall does not open the viewer port

`deploy/kiosk/config/firewall.sh` sets a deny-by-default policy. It permits
outbound HTTPS, DNS and time, and inbound SSH on port 22. It never
permits inbound port 5901, which is the port its own `--headless` path
tells you to connect to. [TREE]

As written, the headless install advertises a VNC address that the
firewall blocks.

Do not open that port. The firewall is right and the advice is wrong.
The correct answer is to reach the viewer through an SSH tunnel, which
port 22 already permits. The steps below do exactly that. This also
solves a security problem you would otherwise have, because a VNC port
open to the internet draws continuous scanning and attack. [WEB]

**REPAIRED.** Issue #88/#95 left the firewall alone and changed the
advice. `deploy/kiosk/install.sh --headless` now prints the tunnel command and
tells you to bind the VNC server to the loopback interface with
`-localhost yes`. `deploy/kiosk/config/firewall.sh` says in its own header why
5901 stays shut, and `tests/test_os_installer_suite.py` fails if any
rule in that file ever opens it.

### Defect four: the installer omits the library that Qt 6.5 and later demand

This is the failure you would find hardest to diagnose, so read it
carefully.

At commit d3cfe99, `deploy/kiosk/install.sh:100-109` listed the Qt support
libraries to install. It named ten of them. It did **not** name
`libxcb-cursor0`. [TREE] The list is now at `deploy/kiosk/install.sh:130-152`.

From Qt 6.5.0 onward, the `xcb` platform plugin refuses to load without
that library. The error message is misleading on purpose:

```
qt.qpa.plugin: From 6.5.0, xcb-cursor0 or libxcb-cursor0 is needed to
load the Qt xcb platform plugin.
qt.qpa.plugin: Could not load the Qt platform plugin "xcb" in ""
even though it was found.
```

[WEB] The words "even though it was found" tell you the plugin exists
but one of its own dependencies is missing.

Your `pyproject.toml` asks for `PySide6>=6.6.0`, so you are firmly in
the affected range. [TREE]

Without this package the application will not open a window at all. It
does not matter how correct the rest of your setup is. Install
`libxcb-cursor0` and the problem disappears.

**REPAIRED.** Issue #88/#95 added `libxcb-cursor0` to the package list.
`tests/test_os_installer_suite.py` holds the whole set of libraries the
xcb platform plugin needs and fails if any of them leaves the list.

If a Qt window ever fails to appear, run the application again with
`QT_DEBUG_PLUGINS=1` set. Qt then prints each plugin it tried and the
reason each one failed. [WEB]

### What the service unit gets right

The rest of `deploy/kiosk/systemd/acervator.service` is sound and you should keep
it. [TREE] It waits for the network and for the clock to synchronise
before it starts, which matters because exchange APIs reject requests
signed with a wrong clock. It restarts the application after a crash,
but not after a clean exit. It gives up after five failures in five
minutes rather than restarting forever. It writes output to the system
journal. It restricts what the process may write.

### What must change in the unit for a cloud machine

Two lines. [TREE]

`Environment=DISPLAY=:0` names the screen attached to a physical
monitor. A cloud machine has no physical monitor and no screen `:0`. The
value must name the virtual screen you create instead.

`ExecStartPre=/usr/local/bin/acervator-preflight.sh` runs checks that
suit a Raspberry Pi. Check 4 looks for a USB hardware key. Check 6 tests
the display server. On a cloud machine you would review these before you
enable them.

`Environment=QT_QPA_PLATFORM=xcb` is correct and should stay. It tells
Qt to draw to an X11 screen, which is what a virtual screen provides.


---

## Drawing without a graphics card

A cheap cloud machine has no graphics card. You are right to ask
whether the animation will survive that. The answer is good, and it
rests on a fact I measured in your own code.

**Your application draws on the processor already.** [TREE] I searched
the whole tree for the parts of Qt that need a graphics card:
`QOpenGLWidget`, `QtQuick`, `QQuickWidget` and QML. The search found
**zero** matches in `src/` and in `main.py`.

Everything you see is Qt Widgets painted with `QPainter`. Qt's own
documentation states that `QPainter` on a widget uses the raster paint
engine, which is a software rasteriser that runs on the processor.
[WEB] It never asks for a graphics card, so it cannot be disappointed
by the absence of one.

The two animated parts confirm this:

- `src/gui/bot_visualizer.py:1725-1727` runs a 33 millisecond timer,
  which is 30 frames per second. Its `paintEvent` at line 409 uses
  `QPainter` with antialiasing. [TREE]
- `src/gui/main_window.py:6555` repaints the dashboard every 2000
  milliseconds. [TREE]

Both are processor work. The question is therefore not whether a graphics card exists. The
question is whether the machine has enough processor cores. Give the
machine 4 virtual cores rather than 2. The drawing and the trading then have room
to run side by side.

### The one part that is different

`src/gui/tradingview_chart.py:28` imports `QWebEngineView`. [TREE] That
widget embeds a full Chromium browser, and Chromium does look for
graphics acceleration. The import sits inside a `try` block and sets
`_HAS_WEBENGINE = False` when it fails, so the application survives
without it. [TREE]

I could not establish how that chart behaves on a machine with no
graphics card. **[UNKNOWN]** Test it. If the chart is slow or blank,
you now know which single widget to blame, and the rest of the
application keeps working.

### What Qt needs on the machine, and what it does not

Install the full set of `libxcb-*` libraries, and `libxcb-cursor0`
above all. [WEB] Those are the real requirement.

You do not need `mesa-utils` or graphics drivers for the widget
drawing. Install `mesa-utils` only if you want the `glxinfo` command
for diagnosis. [WEB]

---

## Where your Coinbase keys would live, and what changes when you move them

Today your API keys sit in `~/.acervator/` on a computer in your home,
behind your own login. Moving them to a rented machine changes who could
reach them. This is a decision about risk, not a file copy. Two facts
from your code should shape that decision.

### The keyring question, and why it turns out not to block you

`src/core/encryption.py:182-256` wraps the operating system credential
store. On a Linux machine with no desktop session there is usually no
such store, so `has_secure_backend` returns false and `store` refuses
to save anything. That sounds like a blocker.

It is not, because **nothing uses it**. [TREE] `main.py:755` constructs
`KeyringManager()` and the variable is never read again. I searched the
whole tree: no other file constructs it, and no live path calls
`store` or `retrieve`. The keyring is dead code in the running
application.

A headless Linux machine will therefore not stop you. Good news for the
plan.

### The finding that matters much more

The keys are described as encrypted. In practice they are not
protected. [TREE]

`src/gui/main_window.py:3701` and `main_window.py:8605` build the
decryption passphrase like this:

```
master = f"qat_{sm.get('username', 'user')}_vault"
```

The passphrase is your username wrapped in fixed text. `settings.json`
holds that username, in the same folder, beside the encrypted keys. Anybody who can read that folder holds both the locked box and
the recipe for its key.

The encryption is therefore real cryptography protecting nothing.
Treat `~/.acervator/` as if it holds your Coinbase keys in plain text,
because in effect it does.

This has one convenient consequence and one uncomfortable one.

The convenient one: the machine can restart on its own and reconnect to
Coinbase without you typing anything. [TREE] That is why the automatic
restart at `main.py:1437` works.

The uncomfortable one: on your desktop, that folder is behind your
Windows login. On a rented machine it is behind an SSH key, the
provider's staff, and any snapshot of the disk. If somebody reaches
that machine, they have your trading keys.

### What to do about it

These are the steps that reduce the exposure, in order of value.

1. **Restrict the Coinbase API key itself.** Coinbase lets you limit
   what a key may do and which internet addresses may use it. Give the
   cloud key trade permission but **not** withdraw permission. Lock it
   to the cloud machine's address. Then a stolen key can trade badly,
   but it cannot move coins out. This is the strongest control
   available, and it sits at the exchange where both machines must
   obey it.
2. **Never open a port to the internet.** Reach the machine through
   SSH only, with a key, and turn off password login.
3. **Encrypt the disk if the provider offers it**, and know that this
   does not protect a running machine.

---

## How you would see the window

You want the real window, wherever the application runs. That means the
Linux machine must draw the window, and something must carry the picture
to you. This section judges the ways to do that.

One property decides the answer, and you did not ask about it. **What
happens when you close your laptop?** The bots must keep trading. A
viewer that stops the application when your connection drops would end
your trading every time your train enters a tunnel.

That property splits every option into two groups.

**Connection-attached.** The screen belongs to the connection. Close the
connection and the screen disappears, and the application dies with it.

**Connection-detached.** A screen runs on the Linux machine on its own.
Viewers attach to it and detach from it. The application never knows.

You need the second group. Nothing in the first group is acceptable,
however good it looks.

### The option to reject first

**Do not use X11 forwarding.** [WEB] Many guides recommend `ssh -X`
because it is the easiest to set up. For you it is the wrong answer,
twice.

Your laptop holds the screen. The application on the Linux machine draws
to it across the connection. When the connection drops, the X library
declares a fatal error and the process exits. The X documentation states
that the program exits if its error handler returns.

Note carefully: `screen`, `tmux` and `nohup` do **not** rescue this. They
protect against a hang-up signal. This is not a hang-up signal. The
application chooses to exit because its screen vanished.

X11 forwarding is also the slowest option for your animation. Qt version
5 and later paint into a picture and send the finished pixels, rather
than sending drawing commands. Over a long link that means a whole
picture per frame, uncompressed. [WEB]

### The options I judged and set aside

| Option | Why I set it aside |
|---|---|
| NoMachine | On a machine with no monitor, the free product cannot make a screen at all. That capability sits in the paid Terminal Server products, and the free edition ended at version 10. [WEB] |
| Apache Guacamole | It is a browser gateway, not a screen. It still needs VNC or RDP underneath, then converts the picture again into browser images. Most machinery, worst animation. [WEB] |
| Sunshine and Moonlight | Fastest in principle, because it encodes video. It captures from a graphics card, which a cheap cloud machine does not have. [WEB] |
| Chrome Remote Desktop | I could not establish whether a Linux session survives a disconnect. A silent failure in the property that matters most is not a risk worth taking. [WEB] |
| RealVNC | Its virtual screen is destroyed on disconnect **by default**, and persistence is a paid feature. [WEB] |

### The three real candidates

**TigerVNC.** A program called Xvnc acts as both the screen and the
viewer server, in one process. It keeps running when nobody is
watching. Three separate timeout settings each default to zero, which
means never give up. Reconnect and your window is exactly where you
left it. [WEB]

**Xpra.** Built for this exact purpose. Its manual describes running a
program, disconnecting, and reconnecting from another machine without
losing any state. It picks its own compression and promotes moving
areas to video encoding automatically, which suits your visualiser
well. It travels over SSH by default and opens no port at all. [WEB]

**xrdp.** Speaks the Microsoft Remote Desktop protocol, so Windows can
connect with the viewer it already has. Version 0.10.2 and later can
encode with H.264, which is the best match for animation of anything
here. Disconnected sessions persist by default. [WEB]

### My recommendation, and what it gives up

**Use TigerVNC, bound to the machine itself, reached through an SSH
tunnel.**

Four reasons, in order of weight.

1. **It keeps your bots alive.** Persistence is the default, not a
   setting you might forget. This is the property you cannot compromise.
2. **Your own repository already chose it.** `deploy/kiosk/install.sh:160`
   installs `tigervnc-standalone-server` on the `--headless` path, and
   `deploy/kiosk/install.sh:354-361` writes a startup file that launches Openbox
   and then the application. [TREE] You are repairing something that
   exists rather than building something new. That is a much smaller
   job, and a much smaller thing to maintain.
3. **Your firewall already fits it.** `deploy/kiosk/config/firewall.sh` permits
   inbound SSH and nothing else. [TREE] The tunnel needs exactly that
   and nothing more. The firewall was right all along, and only the
   printed advice about port 5901 was wrong.
4. **It is the best documented, and you are new to this.** When
   something breaks, you will find an answer.

**What you give up: smoothness.** The VNC protocol works by request.
The viewer asks for an update, and the machine sends the changed
rectangles. When the link cannot keep up, frames are **skipped**, not
queued. [WEB]

The practical effect on your application:

- The dashboard, which repaints every 2 seconds, will look correct and
  feel normal. [TREE]
- The bot visualiser animates at 30 frames per second [TREE], and over
  a long link it will look choppy. That second half is my inference
  from how the protocol works [WEB], not a measurement. It will remain
  correct. It will not be smooth.

Judge that trade honestly. You are watching a trading fleet, not
playing a game. Correct and readable beats smooth. If you try it and
the visualiser is genuinely unusable, the next thing to try is xrdp
version 0.10.2 or later with H.264, which is the better animation
protocol.

### Two warnings before you pick an alternative

If you choose **Xpra**, do not use its seamless mode. Your application
opens an animated frameless splash window (`main.py:1014`). [TREE]
Seamless mode forwards individual windows and is documented as awkward
with unusual window types. Use its desktop mode instead. I could not
establish how Xpra handles your splash. **[UNKNOWN]**

If you choose **xrdp**, test one thing before you trust it: pull the
network cable while connected, then reconnect. A defect was reported
where an unclean drop leaves a grey screen and the session cannot be
recovered without restarting the service. I could not establish whether
current versions still do this. **[UNKNOWN]** Closing a laptop lid is
exactly that kind of drop, so test it deliberately.

### Never open the viewer port to the internet

This is not caution for its own sake. Researchers found 3.4 million
remote-desktop and VNC servers reachable from the internet, and close to
60,000 VNC servers with no password at all. National security agencies
have published warnings about attackers scanning for these ports. [WEB]

The old VNC password scheme accepts only 8 characters.

You will therefore start the screen with `-localhost`, which makes it
refuse every connection except one from the machine itself. You then
build an SSH tunnel, which makes your laptop appear to be that machine.
Your traffic travels inside SSH, which is already encrypted and already
permitted by your firewall.

---

## Building the machine, step by step

Each step says what it is for. Do not skip the reason.

### Step 1 — Stop the desktop copy and take its keys away

Before anything else, close Acervator on your desktop. Then go to
Coinbase and delete the API key that copy uses.

**Why:** this is the two-copy guard. Everything after this step assumes
only one copy can reach your account.

### Step 2 — Rent the machine

Choose **Ubuntu 24.04 LTS**, 4 virtual cores, 8 GB of memory.

**Why Ubuntu 24.04:** it ships Python 3.12, which your installer
demands. Debian 12 does not. [WEB]

**Why 4 cores:** the drawing runs on the processor, because your
application uses no graphics card. Two cores would make the drawing
compete with the trading.

Add your SSH public key when you create the machine. Turn off password
login.

### Step 3 — Log in, then prove you can get back in again

Connect over SSH. Disconnect. Connect again.

**Why:** every later step depends on this working. Prove it while
nothing else can be blamed.

### Step 4 — Check the installer before you run it

The tree now holds a repair for each of the four defects named earlier.
Confirm that those repairs reached the machine you will install on, and
see what the installer would do, with one command:

```
bash deploy/kiosk/install.sh --dry-run --headless
```

**Why:** `--dry-run` needs no root and changes nothing. It prints every
command the installer would run, and then prints
`DRY RUN finished`. If it stops before that line, do not run the real
install.

**What to look for in the output:**

1. It reaches sections `5 / 8` through `8 / 8`. Defect one used to stop
   it at section 4.
2. The `apt-get install` line names `libxcb-cursor0`.
3. The `apt-get install` line names `python3` and not `python3.12`.
4. The VNC advice names an `ssh -L` tunnel and not a public address.

### Step 5 — Install with the headless option

Run the installer with `--headless`.

**Why:** that path installs TigerVNC and writes the startup file
instead of configuring a physical monitor.

### Step 6 — Start the screen, sized correctly

Start the virtual screen at 1920 by 1080, and bind it to the machine
itself with `-localhost`.

**Why 1920 by 1080:** your main window refuses to be smaller than 1400
by 900 (`src/gui/main_window.py:4542`). [TREE] A smaller screen cuts
the window off.

**Why `-localhost`:** it is the security control described above.

### Step 7 — Build the tunnel and look at the empty application

From your laptop, open an SSH tunnel that connects a local port to port
5901 on the machine. Point your VNC viewer at your own machine, not at
the cloud address.

**Why:** the tunnel is the only route in. If you must type the cloud
machine's public address into a VNC viewer, something is wrong.

At this point Acervator should open with no bots and no keys.

**Why this matters:** an empty state folder means no bots exist, so
nothing can auto-start and nothing can trade
(`src/core/state_manager.py:573`). [TREE] You are testing the picture,
not risking money.

### Step 8 — Test the property that matters

Leave the application running. Close your laptop, or disconnect your
network, for several minutes. Then reconnect.

**Why:** you are proving the one property the whole plan rests on. If
the window is still there and still running, the architecture is
correct. If it is not, stop and fix that before you go any further.

Do this test before you put a single key on that machine.

### Step 9 — Judge the picture honestly

Watch the visualiser. Watch the dashboard. Decide whether you can work
with it.

**Why:** this is the moment to change your mind cheaply. Nothing is at
risk yet.

### Step 10 — Make the machine start on its own

Adjust the systemd unit so the virtual screen starts at boot and the
application starts on that screen. Change `DISPLAY` from `:0` to your
virtual screen number, and review the pre-flight checks that expect
Raspberry Pi hardware.

**Why:** if the machine reboots, you want it back without you. Your
credentials decrypt without a typed passphrase, so an unattended
restart does reconnect to Coinbase.

### Step 11 — Only now, move the account across

Create a **new** Coinbase API key for this machine. Give it trade
permission and **not** withdraw permission. Restrict it to the machine's
address.

Copy your settings and your fleet into `~/.acervator/` on the machine.
Enter the new key.

**Why last:** every earlier step could be undone at no cost. This one
cannot.

Then start the application and watch it. Bots will begin to trade about
9.25 seconds after the window appears. Expect that, and be present for
it.

---

## What it costs each month

**I cannot verify any price here.** I read these on vendor pages on
2026-08-23. I did not buy anything. Cloud prices change without notice,
and two of the entries below changed during 2026. Check every number
before you commit. [WEB]

You need roughly 4 virtual cores and 8 GB of memory. The extra cores
are for the drawing, not the trading.

| Provider | Plan | Cores | Memory | Published price each month |
|---|---|---|---|---|
| Hetzner (Germany) | CX33 | 4 | 8 GB | EUR 8.49 before tax |
| DigitalOcean | Basic 8 GB | 4 | 8 GB | USD 48 |
| Akamai (Linode) | Shared 8 GB | 4 | 8 GB | USD 48 |
| AWS Lightsail | General Purpose | 2 | 8 GB | USD 44 |
| Google Cloud | e2-standard-2 | 2 | 8 GB | about USD 49 |

Sources appear at the end of this document. The Google figure came from
a third-party site because the official page would not load, so trust it
least. [WEB]

### Two warnings about cheap options

**Hetzner is the cheapest and carries a policy risk.** Its written terms
prohibit crypto **mining** and say nothing about trading. But Hetzner
stated publicly in 2022 that its ban "includes trading", and it
disconnected more than a thousand Solana nodes in November 2022 with
little warning. [WEB] The written terms and the stated position
disagree. If you want Hetzner, ask their support in writing first. Do
not discover the answer through a locked account holding your keys.

By contrast, the DigitalOcean acceptable-use policy prohibits mining
only, and the AWS acceptable-use policy contains no cryptocurrency
clause at all. [WEB] Trading software is an ordinary network program.

**Do not use the Oracle free tier for this.** [WEB] Oracle reclaims a
free machine when its processor, network and memory all stay below 20
percent over seven days. A trading bot that waits for market conditions
will trip that test and lose the machine. Oracle also cut the free
allowance in half in June 2026 without announcing it, and mailed users
that oversized machines would be terminated. A free machine that
disappears while holding your keys is worse than no machine.

### The cost you should weigh against this

A cloud machine costs about ten to fifty dollars each month, forever. A
small computer at your home costs money once and then costs
electricity. It gives you the same Linux, the same window, and the same
remote viewing, without renting anything and without putting your
trading keys on somebody else's hardware. Your `deploy/kiosk/` folder was
originally written for exactly that machine.

I mention it because you asked for the cloud and I should still tell
you the cheaper answer exists. The cloud wins on one thing: it keeps
running when your house loses power or internet. If that is why you
want it, rent the machine. If it is not, the small computer is better
value.

---

## What can go wrong, and how you would notice

| Symptom | Most likely cause | What to do |
|---|---|---|
| The installer stops early and prints "unbound variable" | You are running a copy from before the issue #88/#95 repair | Update the tree, then prove it with `bash deploy/kiosk/install.sh --dry-run` |
| The installer stops and says it needs Python 3.11 or later | Your machine is Ubuntu 22.04, which ships 3.10 | Rebuild the machine on Ubuntu 24.04 LTS, or on Debian 12 |
| "Could not load the Qt platform plugin xcb ... even though it was found" | `libxcb-cursor0` is missing | Install it, then run again with `QT_DEBUG_PLUGINS=1` if it persists |
| The service restarts five times and then stops | `DISPLAY` names a screen that does not exist | Point `DISPLAY` at your virtual screen number |
| The window opens but is cut off | The virtual screen is smaller than the window | The main window demands at least 1400 by 900. Use 1920 by 1080 |
| The window is smooth locally and slow to you | The link between you and the machine | Choose a machine closer to you, or lower the screen resolution and colour depth |
| Trades appear that you did not expect | Two copies are running | Stop and check both machines at once. This is the money-losing case |
| The exchange rejects requests | The machine clock drifted | The service already waits for clock synchronisation. Check that the time service runs |

### The check you should perform every single time

Before you start Acervator anywhere, ask one question and answer it out
loud: **is it already running somewhere else?**

Log in to Coinbase and look at your open orders and recent fills. If you
see activity you did not expect, a second copy is trading. Stop it
before you start anything.

You have no software guard for this. Until one is built, the procedure
is the guard.

---

## What I could not establish

I list these so you do not mistake my silence for confidence.

1. **I did not build the machine.** Everything about the Linux side of
   this guide comes from reading your code and from vendor
   documentation. I did not rent a machine, install anything, or watch
   your window appear on a remote screen. The first person to test this
   will be you.
2. **I could not measure how the animation feels over a real link.**
   Frame rate over a network depends on your distance from the machine
   and on your own connection. No document can answer that. You must
   try it.
3. **I could not establish how the TradingView chart behaves without a
   graphics card.** It is the one widget that embeds a browser.
4. **I found no published measurement of animated 2D Qt content on a
   machine with no graphics card.** The evidence I found concerns 3D
   work and video. Your application avoids the affected path entirely,
   which is why I still judge the risk low, but I did not find a direct
   measurement.
5. **I could not verify any price.** Every figure is as published, not
   as paid.
6. **I could not read the Oracle and Akamai policy documents.** Their
   servers refused my requests. What I report about Oracle's policy is
   second-hand.
7. **Nobody has run `deploy/kiosk/install.sh` on a real machine.** The issue
   #88/#95 repair added a `--dry-run` mode, and the dry run does reach
   the last line of the script on a machine that is not Debian. That
   proves the CONTROL FLOW completes. It does not prove that
   `apt-get`, `useradd`, `systemctl` and `ufw` all succeed on a real
   target, and it does not prove that a window opens. The first person
   to test that will be you.
8. **I never opened your credentials.** I did not read
   `~/.acervator/`, and nothing in this guide depends on its contents.

---

## Sources I read on the internet

These support the claims marked **[WEB]**. Everything marked **[TREE]**
came from your own repository and needs no external source.

**On viewing a remote Linux screen**

- X exits when its connection breaks — https://www.x.org/releases/current/doc/man/man3/XSetErrorHandler.3.xhtml
- Xlib default error handlers — https://tronche.com/gui/x/xlib/event-handling/protocol-errors/default-handlers.html
- Qt 5 is slow over forwarded X11 — https://forum.qt.io/topic/67371/x11-forwarding-slow-on-qt-5-applications
- Remote X performance study, Berkeley — https://dav.lbl.gov/archive/Events/SC08/RemoteX/index.html
- Xvfb manual — https://manpages.debian.org/testing/xvfb/Xvfb.1.en.html
- x11vnc manual, and its exit-on-disconnect default — https://manpages.debian.org/testing/x11vnc/x11vnc.1.en.html
- TigerVNC Xvnc manual, and its three zero timeouts — https://tigervnc.org/doc/Xvnc.html
- TigerVNC security advice — https://wiki.archlinux.org/title/TigerVNC
- Red Hat on binding VNC to localhost — https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/7/html/system_administrators_guide/ch-tigervnc
- The VNC protocol asks for updates — https://github.com/rfbproto/rfbproto/blob/master/rfbproto.rst
- RealVNC destroys the screen on disconnect by default — https://help.realvnc.com/hc/en-us/articles/4415094277521-How-do-I-make-virtual-desktop-sessions-persistent-when-using-RealVNC-Server-s-Virtual-Mode-daemon
- xrdp shipped defaults, KillDisconnected — https://github.com/neutrinolabs/xrdp/blob/devel/sesman/sesman.ini.in
- xrdp H.264 encoding, and its limits — https://github.com/neutrinolabs/xrdp/wiki/H.264-encoding
- xrdp grey screen after an unclean drop — https://github.com/neutrinolabs/xrdp/issues/468
- Xpra manual, disconnect and reconnect without losing state — https://man.archlinux.org/man/xpra.1
- Xpra picture and video encodings — https://github.com/Xpra-org/xpra/blob/master/docs/Usage/Encodings.md
- Xpra over SSH, no open port — https://github.com/Xpra-org/xpra/blob/master/docs/Network/SSH.md
- NoMachine needs a paid product for a screen on a headless host — https://forum.nomachine.com/topic/virtual-desktop-in-free-version
- NoMachine ended its free edition at version 10 — https://www.nomachine.com/what-s-new-in-nomachine
- Guacamole architecture — https://guacamole.apache.org/doc/gug/guacamole-architecture.html
- Sunshine needs a graphics card and a display — https://docs.clore.ai/guides/gaming-and-streaming/sunshine-moonlight
- 3.4 million exposed remote-desktop and VNC servers — https://industrialcyber.co/industrial-cyber-attacks/forescout-finds-3-4-million-rdp-and-vnc-servers-exposed-raising-risks-to-ot-and-enterprise-networks/
- Tens of thousands of VNC servers with no password — https://www.rapid7.com/blog/post/2020/10/09/nicer-protocol-deep-dive-internet-exposure-of-vnc/

**On drawing, dependencies and providers**

- Qt raster paint engine — https://wiki.qt.io/Qt5GraphicsOverview
- Qt Linux requirements, the `libxcb` list — https://doc.qt.io/qt-6/linux-requirements.html
- Qt plugin diagnosis with `QT_DEBUG_PLUGINS` — https://doc.qt.io/qt-6/deployment-plugins.html
- Qt platform plugin selection — https://doc.qt.io/qt-6/qpa.html
- Mesa software rendering variables — https://docs.mesa3d.org/envvars.html
- Mesa llvmpipe — https://docs.mesa3d.org/drivers/llvmpipe.html
- Debian 12 ships Python 3.11 — https://packages.debian.org/bookworm/python3
- Hetzner price change, June 2026 — https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
- Hetzner terms, mining clause — https://www.hetzner.com/legal/terms-and-conditions/
- Hetzner statement that the ban includes trading — https://www.theblock.co/post/165976/host-of-10-of-ethereum-nodes-prohibits-crypto-usage-discussing-consequences
- DigitalOcean prices — https://www.digitalocean.com/pricing/droplets
- DigitalOcean acceptable use — https://www.digitalocean.com/legal/acceptable-use-policy
- Akamai and Linode prices — https://www.akamai.com/cloud/pricing/north-america
- AWS Lightsail prices — https://aws.amazon.com/lightsail/pricing/
- AWS acceptable use — https://aws.amazon.com/aup/
- Oracle free tier limits — https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Oracle free tier reduction, June 2026 — https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/
