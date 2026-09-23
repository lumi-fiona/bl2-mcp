#!/usr/bin/env bash
# Launch Borderlands 2 and stop at the main menu. No keys are ever sent.
#
# This used to start the game itself and wait 3.5 minutes for the pack's "core.py@... loaded" log
# line. That line is written, at the main menu (2026-09-23: "up" after 66 s), but the title screen
# walks itself to the menu after a delay nothing here controls: 66 s, 158 s (ticket 01), and past
# the whole wait in ticket 06, which printed FAILED while cycle.sh --menu - which walks the title
# screen itself through the bridge - reached the menu in about 50 s the same session. It also
# killed with a fixed 2 s wait, where cycle.sh waits until the old process is really gone.
exec bash "$(dirname "$0")/cycle.sh" --menu
